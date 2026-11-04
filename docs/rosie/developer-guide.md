# Developer Guide

## Requirements

- Python 3.12+
- Docker Compose for the complete local stack
- llama.cpp-compatible chat and embedding GGUF files and sufficient host resources

## Development

Install the project and test extras with `pip install -e '.[dev]'`. Run the API with `uvicorn rosie.main:app --reload` after setting service URLs in the environment. Run tests with `pytest`.

For Compose, put compatible chat and embedding GGUF files in the model directory (default `./models`) and set their filenames in `.env` if they differ from `.env.example`; then start services with `docker compose up --build` and use `http://localhost:8001` or `http://<host-ip>:8001` from another LAN device. ROSIE is published on host network interfaces; Qdrant and both llama.cpp servers are reachable only inside the Compose network. Restrict TCP port 8001 in the host firewall to trusted networks. Store source material under `knowledge/`; use `knowledge/runbooks/` for runbooks. In the chat page, use the **Sync sources** link beneath the prompt to refresh configured web sources on demand. Its adjacent status reflects server-side startup, scheduled, and manual syncs. The prompt stays disabled until the initial source sync succeeds. The equivalent API endpoint is `POST /api/ingest/sources`.

For local development outside Compose, ROSIE uses `http://localhost:8080/v1` for llama.cpp chat, `http://localhost:8081/v1` for embeddings, and `http://localhost:6333` for Qdrant by default. Start the two llama.cpp servers separately with the selected GGUFs. To make the page available on the LAN, start ROSIE with `uvicorn rosie.main:app --reload --host 0.0.0.0 --port 8001`. Restrict access with the host firewall.

## Automatic Source Sync

ROSIE starts a background source sync on every application startup, keeping the
page and health endpoint available while ingestion runs. The prompt and chat API
stay locked until a sync completes without crawl errors. Failed or partial initial
syncs retry every 30 seconds; the manual link and host timer can also retry them.
`GET /api/ingest/sources/status` exposes readiness, active sync state, the last
successful timestamp, counts, and the latest error. The page polls this endpoint
every three seconds instead of trusting browser storage. Later refresh failures
retain readiness from a successful initial sync. Every restart resets readiness
and requires a fresh sync, even if indexed documents already exist.

Startup syncing is required even when `SOURCE_SYNC_ENABLED=false`; that setting
only controls the host timer worker. Readiness and the ingestion lock are held in
the API process, so keep the supplied single-worker Uvicorn deployment. Multiple
workers would require shared readiness and locking before being supported.

The host systemd timer in `deploy/host/rosie-source-sync.timer` starts a short-lived
worker every minute. The worker reads `.env` on every invocation and calls the
existing `POST /api/ingest/sources` endpoint only when the configured interval has
elapsed. No separate daemon or in-app scheduler is needed.

| Setting | Default | Purpose |
| --- | --- | --- |
| `SOURCE_SYNC_ENABLED` | `true` | Allow scheduled syncs; `false` skips them without disabling manual sync. |
| `SOURCE_SYNC_INTERVAL_SECONDS` | `3600` | Minimum seconds between scheduled attempts; must be positive. |
| `SOURCE_SYNC_API_URL` | `http://127.0.0.1:8001/api/ingest/sources` | API URL reachable from the host worker. |
| `SOURCE_SYNC_TIMEOUT_SECONDS` | `3600` | HTTP timeout in seconds; must be positive. |

These are environment-backed `Settings` fields and are also passed into the app
by Compose for future configuration UI support. There is no settings UI or write
API yet. Future UI configuration should persist these values to the host `.env`;
the container does not currently have write access to it. Do not mount it writable
solely for scheduling. The worker sees saved changes at the next minute tick,
without a systemd reload. Its `.env` controls scheduling, while the running API's
settings control source URLs and crawl limits; recreate the app after changing
those API settings through Compose.

### Installation

The supplied service assumes a checkout at `/opt/rosie` with a Python 3.12+
environment at `/opt/rosie/.venv`. On the host, create that environment and install
the worker's dependencies:

```bash
cd /opt/rosie
python3 -m venv .venv
.venv/bin/python -m pip install httpx pydantic-settings
```

For a different checkout location, edit `WorkingDirectory` and the Python path in
`ExecStart` in the service before installing it. The restricted dynamic service
user must be able to traverse the checkout and read its Python environment and
`.env`. If these are private to a deployment account, use a service override with
`DynamicUser=no` and `User=<deployment-account>` instead of making private files
world-readable. Keep `StateDirectory` and the state-file argument aligned.

Once the ROSIE API is running, an administrator can install and enable the units:

```bash
sudo install -m 0644 deploy/host/rosie-source-sync.service /etc/systemd/system/
sudo install -m 0644 deploy/host/rosie-source-sync.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now rosie-source-sync.timer
systemctl list-timers rosie-source-sync.timer
journalctl -u rosie-source-sync.service
```

Adding these files does not install or activate anything automatically.

### Timing and Failure Handling

The first eligible tick syncs immediately. Later attempts are spaced from the last
attempt's start, rounded to the timer's minute-level resolution (plus systemd's
timer accuracy window); sub-minute intervals do not produce sub-minute polling.
`Persistent=true` catches up a missed timer tick after downtime, but does not
replay every missed sync. The state survives restarts in
`/var/lib/rosie-source-sync/last-attempt`.

Systemd does not start another instance of the same active one-shot service, so
scheduled syncs cannot overlap one another. The API also rejects overlapping
startup, manual, or scheduled syncs with HTTP 409. The worker records an attempt before fetching, so failed attempts
also wait for the configured interval instead of retrying every minute. Network
errors, HTTP errors, malformed responses, and partial crawl errors produce a
failed unit status and journal entry. Successful runs log the API's counts.

The existing crawler discovers linked HTML pages and the indexer avoids embedding
unchanged content. This does not add conditional HTTP caching, deletion of missing
pages, or discovery of unlinked documents. The browser displays the shared server
sync status, including successful host-scheduled runs.

## Change Guidelines

Keep integrations behind small adapters, do not add infrastructure actions to v0.1, and add focused tests for changes to ingestion, retrieval metadata, runbook structure, publishing, or audit events.
