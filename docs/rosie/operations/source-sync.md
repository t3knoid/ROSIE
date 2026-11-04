# Source Sync

ROSIE indexes a documentation site and a runbook index page, set by `DOCUMENTATION_SOURCE_URL` and `RUNBOOK_SOURCE_URL` (see [configuration](../configuration.md#documentation-sources)). This page explains when syncs run, how readiness works, and how to install the optional scheduled sync.

## When Syncs Run

| Trigger | Notes |
| --- | --- |
| App start | Always runs, in the background. Retries every 30 seconds until one sync finishes with no errors. |
| **Sync sources** link on the chat page | Runs a sync immediately. |
| `POST /api/ingest/sources` | The same as the link; the request returns when the sync finishes. |
| Host timer (optional) | Runs when `SOURCE_SYNC_INTERVAL_SECONDS` has passed since the last scheduled attempt. |

Only one sync runs at a time; a second request gets HTTP 409. The status line under the prompt and `GET /api/ingest/sources/status` show the current state, the last successful sync, page and passage counts, and the latest error.

## Readiness

Chat stays disabled, and `POST /api/chat` returns 503, until a sync finishes **with no errors** after the app starts. This happens on every restart, even when Qdrant already holds indexed content. Once ready, later failed syncs do not disable chat again.

Any page error counts, including a single broken link or a link that redirects. If chat stays locked after a restart:

1. Read the error under **Sync sources**, or run `curl -s http://localhost:8001/api/ingest/sources/status`.
2. Fix or remove the failing links on the source site, or adjust the crawl limits in `.env`.
3. Wait for the 30-second retry, or click **Sync sources**.

## What a Sync Does

- **Documentation** is crawled recursively from the start page.
- **Runbooks** are the pages linked from the runbook index's main content; links in its header, navigation, and footer are ignored. Links inside runbooks are not followed.
- **The runbook index page** is stored as a `document`, not a runbook. Its first passage says that it is the runbook index, how many runbooks it links to, and its categories, so questions such as "Is there a list of runbooks?" find it.
- Only same-origin HTTPS pages ending in `.html` or `.htm` (or `/`) are followed, up to `WEB_SOURCE_MAX_PAGES` per source. Redirects are not followed.
- `/index.html` at the site root is treated as the same page as `/`.
- A URL found by both crawls is stored once, as a runbook. If an older index stored a page under both kinds, the next sync corrects it.
- Unchanged pages are not re-embedded, so repeat syncs are fast after the first.
- Pages that are no longer linked are **not** removed from the index.

Counts in the result describe the pages processed in that sync, not the total in the index.

## Scheduled Sync (Optional Host Timer)

The systemd timer in `deploy/host/` runs a short-lived worker every minute. The worker reads `.env` from its checkout each time, and calls `POST /api/ingest/sources` only when the configured interval has passed. No daemon or in-app scheduler is involved.

### Install

The supplied service assumes a checkout at `/opt/rosie` with a Python 3.12+ environment at `/opt/rosie/.venv`:

```bash
cd /opt/rosie
python3 -m venv .venv
.venv/bin/python -m pip install httpx pydantic-settings
```

For another location, edit `WorkingDirectory` and the Python path in `ExecStart` in `deploy/host/rosie-source-sync.service` before installing it. The service runs as a restricted dynamic user, which must be able to read the checkout, its virtual environment, and `.env`. If those are private to a deployment account, use a service override with `DynamicUser=no` and `User=<deployment-account>` rather than making the files world-readable.

Once ROSIE is running, install and enable the units:

```bash
sudo install -m 0644 deploy/host/rosie-source-sync.service /etc/systemd/system/
sudo install -m 0644 deploy/host/rosie-source-sync.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now rosie-source-sync.timer
systemctl list-timers rosie-source-sync.timer
```

Check results with `journalctl -u rosie-source-sync.service`.

### Timing and Failures

- The first tick after installation syncs immediately. Later attempts are spaced from the start of the previous attempt, to the nearest minute.
- An attempt is recorded before it runs, so a failed sync waits a full interval rather than retrying every minute. The app's own 30-second retry still applies until it is first ready.
- `Persistent=true` runs one catch-up tick after downtime; missed syncs are not replayed.
- The last attempt time is kept in `/var/lib/rosie-source-sync/last-attempt` and survives reboots.
- Network errors, HTTP errors, and partial crawl errors mark the run as failed in the journal. Successful runs log the counts.
- Changes to `SOURCE_SYNC_*` in `.env` apply at the next minute, without reloading systemd. `SOURCE_SYNC_ENABLED=false` stops scheduled syncs only.
