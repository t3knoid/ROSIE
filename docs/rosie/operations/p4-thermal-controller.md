# Tesla P4 Thermal Controller: Deployment and Operations

This guide deploys the optional host-side fan controller in `deploy/host/`. The example hardware is a Tesla P4 in a Supermicro X10 system. The controller is **not part of ROSIE's request path**: it runs as a privileged systemd service, reads host GPU and fan telemetry, and may write a BMC fan mode. ROSIE only reads the controller's JSON status file through `GET /api/health/gpu`.

This procedure changes physical fan behavior. The controller has fake-backed tests, but has not been validated against your actual BMC. Do not enable it until the model, raw command mapping, and dry-run output have been reviewed by the system owner.

## Components and Data Flow

```text
systemd p4-thermal.service (host root)
  -> nvidia-smi and ipmitool sensor reads
  -> optional BMC fan-mode write
  -> /run/p4-thermal/status.json
  -> read-only bind mount in rosie-app
  -> GET /api/health/gpu
```

The controller requires host `nvidia-smi`, `ipmitool`, Python 3, and access to `/dev/ipmi0`. The systemd unit starts it before Docker during boot and runs an `ExecStopPost` command that requests Full fan mode if the service exits. Compose mounts `/run/p4-thermal` read-only into the app container. ROSIE does not run `nvidia-smi`, invoke `ipmitool`, set fan modes, or add this status to the audit log.

## Fan Policy

The defaults in `p4-thermal.py` are:

| Condition | Controller behavior |
| --- | --- |
| Valid GPU temperature at or above 84 C | Request Full fan mode immediately. |
| Normal startup below 84 C | Begin in Optimal mode. |
| Already in Full, temperature in the 56-83 C hysteresis band | Hold Full. |
| Already in Full, temperature at or below 55 C continuously for 120 seconds | Return to Optimal. |
| First or second consecutive GPU read failure | Keep the current mode; on a fresh startup, the initial mode is Optimal. |
| Third consecutive GPU read failure | Request Full as a fail-safe. |
| Service stop, including a crash | `ExecStopPost` requests Full. |
| Mode unchanged for 60 seconds | Re-send the requested mode to the BMC. |

Status is `warning` at 80 C or above, and `critical` at 85 C or above or when thermal throttling is detected. `error` means the controller could not read the GPU. The controller's `fan_mode` is the mode it last successfully requested, not independent confirmation of the BMC's selected profile; use reported RPMs and BMC tools to verify physical behavior.

The cool-hold timer applies when transitioning from an already-Full mode back to Optimal. On initial startup below 84 C, the code begins in Optimal immediately. If startup should instead require a full two-minute cool period, change and test that behavior before deployment.

## 1. Confirm Host and BMC Prerequisites

Run these read-only checks from the repository root:

```sh
command -v python3 nvidia-smi ipmitool
nvidia-smi
sudo test -c /dev/ipmi0 && echo 'IPMI device is present'
sudo ipmitool mc info
sudo ipmitool sdr type Fan
```

Confirm the BMC is the expected Supermicro X10 generation, that fan sensors return plausible RPM values, and that your board/firmware uses the documented raw fan-mode mapping. The script's raw command is specific to Supermicro X9/X10 BMCs; do not assume it applies to another model. The Full mode used by the shutdown handler is an actuator command, not a read-only operation.

Check the exact throttle-reason value format from this host:

```sh
nvidia-smi --query-gpu=clocks_event_reasons.active --format=csv,noheader,nounits
nvidia-smi -q -d PERFORMANCE
```

The controller currently parses the queried reason field as a hexadecimal bitmask. Compare the first command's output with the second. If it returns descriptive text rather than a hex value, the controller's `thermally_throttled` flag may not be reliable; fix and test that parser before relying on `critical` status for thermal throttling.

## 2. Inspect the Defaults and Run a No-Write Dry Run

Review supported thresholds and options:

```sh
python3 deploy/host/p4-thermal.py --help
```

Run one sensor-reading cycle as root, directing its status output to `/tmp` so it cannot overwrite the live status file:

```sh
sudo python3 deploy/host/p4-thermal.py \
  --once --dry-run \
  --status-path /tmp/p4-thermal-dry-run.json
sudo python3 -m json.tool /tmp/p4-thermal-dry-run.json
```

`--dry-run` does not send the raw fan-mode command, but it does execute `nvidia-smi` and `ipmitool sdr type Fan` to read sensors. Its `fan_mode` is the mode it would request, not the current physical BMC mode. Confirm temperatures, clock fields, throttle reasons, fan RPMs, and any entries under `errors`. This does not test the BMC write command. Do not use `--once` without `--dry-run` as a preliminary check: it performs a normal control cycle and may change the BMC fan mode.

## 3. Install the Host Service

Install the script and unit as root-owned files, then validate the unit before enabling it:

```sh
sudo install -o root -g root -m 0755 \
  deploy/host/p4-thermal.py /usr/local/bin/p4-thermal.py
sudo install -o root -g root -m 0644 \
  deploy/host/p4-thermal.service /etc/systemd/system/p4-thermal.service
sudo systemd-analyze verify /etc/systemd/system/p4-thermal.service
```

The unit creates `/run/p4-thermal` with mode 0755. Its status file is mode 0644 so the containerized app can read it. The unit orders itself before Docker at boot; it does not restart Docker or manage ROSIE.

Only after reviewing the dry-run output, BMC model, and raw mode mapping, enable the service. This step starts automatic fan control:

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now p4-thermal.service
sudo systemctl status p4-thermal.service --no-pager
sudo journalctl -u p4-thermal.service -n 50 --no-pager
```

The service polls every five seconds by default. It sets Full at 84 C or above, and reasserts the mode every 60 seconds. Check actual fan RPM changes and temperatures; do not rely only on a successful systemd status.

## 4. Connect the Status File to ROSIE

The Compose file must contain the read-only mount:

```yaml
- /run/p4-thermal:/run/p4-thermal:ro
```

The app router reads `/run/p4-thermal/status.json` by default. Recreate the app container after the host service has created the directory, so the bind mount is established:

```sh
sudo docker compose config --quiet
sudo docker compose up -d --build --force-recreate app
sudo docker compose ps
```

Read the host file and query the read-only ROSIE endpoint:

```sh
sudo python3 -m json.tool /run/p4-thermal/status.json
curl --fail --silent --show-error http://127.0.0.1:8001/api/health/gpu | python3 -m json.tool
```

The endpoint adds `age_seconds` and `stale`; by default, data older than 30 seconds is marked stale. If the file is absent or unreadable, it returns `available: false` with a reason rather than failing ROSIE's normal health endpoint. `ROSIE_GPU_STATUS_PATH` and `ROSIE_GPU_STATUS_MAX_AGE` can override the endpoint's path and freshness limit. Do not publish this telemetry endpoint to untrusted networks; the current ROSIE API is intended for trusted networks.

The Operations Desk hardware panel shows the first GPU's model (`gpu.name`) and
used/total VRAM in MiB (`gpu.memory_used_mib` / `gpu.memory_total_mib`), including
the percentage used. It refreshes every 10 seconds while the page is visible;
the host controller samples every five seconds by default. Missing model or memory
readings are labeled unavailable, and stale readings are not displayed as live.
Older installed controllers already report memory but must be updated using the
reviewed host-service procedure above to include the model name. Updating this
repository alone does not update the installed host service.

## 5. Tune Thresholds

All controller thresholds are command-line flags. To persist overrides under systemd, create a drop-in rather than editing the installed unit:

```sh
sudo systemctl edit p4-thermal.service
```

Use a complete `ExecStart` override, preserving the executable and adding only reviewed options. For example, to poll every three seconds while keeping the documented 84/55 C thresholds:

```ini
[Service]
ExecStart=
ExecStart=/usr/bin/python3 /usr/local/bin/p4-thermal.py --interval 3 --full-above 84 --optimal-below 55 --cool-hold 120
```

Then reload and restart, understanding that the unit's stop hook requests Full during the restart:

```sh
sudo systemctl daemon-reload
sudo systemctl restart p4-thermal.service
sudo systemctl status p4-thermal.service --no-pager
```

The Tesla P4 previously reached 81 C and has reported Xid 79 (“GPU has fallen off the bus”). Fan control cannot repair a PCIe, power, driver, or hardware fault. Do not treat this controller as a substitute for stabilizing the GPU, and inspect system logs and physical cooling if Xid errors recur.

## Stop, Disable, or Roll Back

Stopping or disabling the service requests Full fan mode by design. Before stopping it, confirm that Full is acceptable for the chassis and workload:

```sh
sudo systemctl stop p4-thermal.service
sudo systemctl disable p4-thermal.service
```

The ROSIE endpoint will continue to return its last status file until it becomes stale. To stop exposing the status file through ROSIE, remove the bind mount from Compose and recreate the app; do not remove the controller or BMC access by changing ROSIE's application permissions.

## Known Validation Limits

The host controller tests use mocked `nvidia-smi` and `ipmitool`; the status API tests use temporary files. They validate parsing, hysteresis, fail-safe decisions, and JSON handling, but do not validate this host's BMC raw command, actual fan RPM response, thermal behavior, or NVIDIA throttle-reason output. Verify those on the exact server/BMC firmware before unattended use. Do not install or enable this controller based only on passing unit tests.
