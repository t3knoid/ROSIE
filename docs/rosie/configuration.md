# Configuration

ROSIE is configured almost entirely through the `.env` file in the repository root. Start from the example:

```sh
cp .env.example .env
```

Every setting has a working default, so `.env` only needs the values you want to change. This page lists every setting, what reads it, and what to restart after changing it.

## Where Settings Are Read

ROSIE runs as several services, and they read their settings in different ways:

| Settings | Read by | How |
| --- | --- | --- |
| `LLAMA_*` model files and GPU settings, `RUNBOOK_PUBLISH_PATH` | Docker Compose | Substituted into `docker-compose.yml` when the stack starts. |
| All other ROSIE settings | The ROSIE app container | Compose passes the whole `.env` to the app (`env_file`). Unknown names are ignored. |
| Container paths and the Qdrant URL | Fixed in `docker-compose.yml` | Not configurable through `.env`; see [Fixed Container Settings](#fixed-container-settings). |
| `SOURCE_SYNC_*` | The optional host timer worker | Reads `.env` in its own checkout (`/opt/rosie/.env` by default) every minute. |
| Thermal thresholds | The optional `p4-thermal` host service | Command-line flags in a systemd drop-in. |
| `system-prompt.md` | The ROSIE app | Read on every request from `docs/rosie/system-prompt.md`. |

Setting names are case-insensitive for the app. Outside Docker (local development), the app reads `.env` from its working directory, and environment variables take precedence.

## Applying Changes

| What you changed | What to run |
| --- | --- |
| App settings (most of this page) | `sudo docker compose up -d app` |
| Model files, GPU layers, context size, parallel slots, micro-batch size | `sudo docker compose up -d llama-chat llama-embeddings` |
| `LLAMA_CHAT_MODEL` or `LLAMA_EMBEDDING_MODEL` (aliases) | `sudo docker compose up -d`, which updates the app and the llama.cpp server that uses the alias |
| `RUNBOOK_PUBLISH_PATH` | `sudo docker compose up -d app` |
| The embedding model file | Re-index; see [Changing the Embedding Model](#changing-the-embedding-model) |
| `docs/rosie/system-prompt.md` | Nothing; the next question uses it |
| `SOURCE_SYNC_*` in the host checkout's `.env` | Nothing; the timer reads it at the next minute |
| Thermal controller flags | `sudo systemctl daemon-reload && sudo systemctl restart p4-thermal.service` |
| Python code or the Dockerfile | `sudo docker compose up -d --build app` |

`docker compose up -d` recreates only the services whose configuration changed. Recreating the app resets source sync readiness: chat is unavailable until the startup sync finishes.

## Models and GPU

These control the two llama.cpp servers. Models are loaded from local GGUF files; the README has download commands for the defaults. See the [GPU acceleration guide](operations/gpu-acceleration.md) for tuning on an 8 GB card.

| Setting | Default | Description |
| --- | --- | --- |
| `LLAMA_MODELS_PATH` | `./models` | Host directory containing the GGUF files, mounted read-only into both servers. |
| `LLAMA_CHAT_MODEL_FILE` | `Llama-3.2-3B-Instruct-Q4_K_M.gguf` | Chat model file name in `LLAMA_MODELS_PATH`. |
| `LLAMA_EMBEDDING_MODEL_FILE` | `nomic-embed-text-v1.5.Q4_K_M.gguf` | Embedding model file name. The model must support llama.cpp embedding mode. |
| `LLAMA_CHAT_MODEL` | `local-chat` | Name the chat server exposes and ROSIE requests. Only needs to match on both sides, which Compose does for you. |
| `LLAMA_EMBEDDING_MODEL` | `local-embedding` | Same, for the embedding server. |
| `LLAMA_N_GPU_LAYERS` | `99` | Model layers to place on the GPU, for both servers. `99` means all. Lower it if a server runs out of VRAM; the rest run on the CPU. |
| `LLAMA_CTX_SIZE` | `10240` | Chat context size in tokens. Must hold the system prompt, evidence, question, and answer. Larger values use more VRAM. |
| `LLAMA_PARALLEL` | `1` | Requests each server handles at once. Each extra slot needs more VRAM. |
| `LLAMA_EMBEDDING_UBATCH_SIZE` | `1024` | Embedding micro-batch size in tokens. Must be at least the longest passage (about 300 tokens by default); larger values use more memory. |
| `LLAMA_CHAT_BASE_URL` | `http://llama-chat:8080/v1` in Compose; `http://localhost:8080/v1` otherwise | Chat server API URL. Change only to use a server outside Compose. |
| `LLAMA_EMBEDDING_BASE_URL` | `http://llama-embeddings:8081/v1` in Compose; `http://localhost:8081/v1` otherwise | Embedding server API URL. |

Review each model's license before use. The default chat model is subject to Meta's Llama 3.2 license.

### Changing the Embedding Model

Stored passages keep the vectors made by the embedding model that indexed them, and ROSIE skips re-embedding text that has not changed. After switching embedding models, existing vectors no longer match new queries, and a model with a different vector size cannot write to the existing collection at all.

To re-index, point ROSIE at a new, empty collection and let the startup sync fill it:

```sh
echo 'QDRANT_COLLECTION=rosie_documents_v2' >> .env
sudo docker compose up -d
```

Then re-run `POST /api/ingest/local` or re-upload any files that were not from the configured web sources. The old collection stays in Qdrant until you delete it.

## Answers and Retrieval

| Setting | Default | Description |
| --- | --- | --- |
| `CHAT_EVIDENCE_LIMIT` | `2` | Passages given to the chat model per question, plus the best-matching runbook passage when it is not already among them. More passages give more context but slow down answers. |
| `CHAT_MAX_OUTPUT_TOKENS` | `512` | Maximum answer length in tokens. Raise it if answers are cut off. Runbook drafts are not limited by this. |
| `RELEVANCE_THRESHOLD` | `0.35` | Minimum similarity (0 to 1) for a passage to count as evidence. Raise it to drop weak matches; lower it if relevant passages are missed. Also decides whether a runbook gap is reported. |
| `QDRANT_COLLECTION` | `rosie_documents` | Qdrant collection that stores passages. |

Documents are split into passages at their headings (HTML `h1`-`h4`, Markdown `#`-`####`), and each passage starts with its page title and section, such as `Home Lab Platform Overview › Platform Foundation › Storage & Data Protection:`. Short subsections are combined with their parent section; long sections are split into passages of up to about 1,200 characters that overlap by about 160. Site navigation, headers, and footers are not indexed. These sizes are not configurable.

## Documentation Sources

ROSIE indexes two websites: a documentation site, crawled recursively, and a runbook index page, whose linked pages are indexed as runbooks. It syncs them at every app start, when you click **Sync sources**, when `POST /api/ingest/sources` is called, and on the optional host timer.

| Setting | Default | Description |
| --- | --- | --- |
| `DOCUMENTATION_SOURCE_URL` | `https://homelab.refol.us/` | Start page of the documentation crawl. Must be an HTTPS URL without credentials. |
| `RUNBOOK_SOURCE_URL` | `https://homelab.refol.us/runbooks.html` | Runbook index page. Pages linked from its main content (not header, navigation, or footer) are indexed as runbooks; the index itself is not. |
| `WEB_SOURCE_MAX_PAGES` | `100` | Maximum pages fetched per source, including the start page. |
| `WEB_SOURCE_TIMEOUT_SECONDS` | `15` | Timeout for each page request. |
| `WEB_SOURCE_MAX_PAGE_BYTES` | `2000000` | Pages larger than this are skipped and reported as errors. |

The crawler follows links only on the same host and port, over HTTPS, to paths ending in `.html` or `.htm` (or `/`). It does not follow redirects; a redirecting link is reported as an error.

Chat stays unavailable until one sync finishes with no errors. A single broken link on either site keeps chat locked after a restart, so fix or remove broken links on the source sites. The error appears under **Sync sources** and in `GET /api/ingest/sources/status`; see [source sync](operations/source-sync.md#readiness).

Local files and uploads are separate from these sources. See the API reference at `/docs` for `POST /api/ingest` and `POST /api/ingest/local`.

## Scheduled Sync (Host Timer)

The optional host timer re-syncs the sources periodically. These settings are read by the timer worker from its checkout's `.env`, not by the app. See the [source sync guide](operations/source-sync.md#scheduled-sync-optional-host-timer) for installation.

| Setting | Default | Description |
| --- | --- | --- |
| `SOURCE_SYNC_ENABLED` | `true` | `false` stops scheduled syncs. Startup and manual syncs still run. |
| `SOURCE_SYNC_INTERVAL_SECONDS` | `3600` | Minimum time between scheduled attempts. The timer checks once a minute. |
| `SOURCE_SYNC_API_URL` | `http://127.0.0.1:8001/api/ingest/sources` | Sync endpoint as reached from the host. Update it if you change the published port. |
| `SOURCE_SYNC_TIMEOUT_SECONDS` | `3600` | How long the worker waits for a sync to finish. |

## Storage

| Setting | Default | Description |
| --- | --- | --- |
| `RUNBOOK_PUBLISH_PATH` | `./docs/rosie/generated-runbooks` | Host directory where `POST /api/runbooks/publish` writes Markdown drafts, such as a checkout of your runbook Git repository. Docker creates it, owned by root, if it does not exist. ROSIE never commits. |

Other data locations are fixed:

| Data | Location |
| --- | --- |
| Indexed passages | Docker volume `qdrant-data` |
| Audit log (JSON Lines) | `/app/data/audit.jsonl` in the Docker volume `rosie-audit`. Read it with `sudo docker compose exec app cat /app/data/audit.jsonl`. |
| Local documents for `POST /api/ingest/local` | `./knowledge` on the host, read-only. Files in `runbooks/` subdirectories or with "runbook" in the name are indexed as runbooks. |

## Organization and Prompt Context

The system prompt in [system-prompt.md](system-prompt.md) contains placeholders such as `{{ORGANIZATION_NAME}}`. ROSIE fills each from the setting of the same name when it answers. The defaults describe a documentation-only homelab deployment; set the ones that describe yours. Any placeholder without a matching setting reads "Not configured".

| Setting | Default | Tells the model |
| --- | --- | --- |
| `ORGANIZATION_NAME` | `Not configured` | Who ROSIE works for. |
| `ENVIRONMENT_NAME` | `Local ROSIE instance` | The environment's name. |
| `ENVIRONMENT_TYPE` | `Documentation-only MVP` | The kind of environment, such as homelab or production. |
| `DOCUMENTATION_SOURCES` | The homelab site, local documents, and uploads | Where documentation comes from. Update it if you change `DOCUMENTATION_SOURCE_URL`. |
| `RUNBOOK_SOURCES` | The homelab runbook index, local runbooks, and uploads | Where runbooks come from. Update it if you change `RUNBOOK_SOURCE_URL`. |
| `INCIDENT_SOURCES` | `Not configured` | Where incident history is kept. |
| `ARCHITECTURE_SOURCES` | Indexed local architecture documents | Where architecture documentation is kept. |
| `INFRASTRUCTURE_CONNECTORS` | None | Infrastructure access. ROSIE v0.1 has none. |
| `OBSERVABILITY_CONNECTORS` | None | Monitoring access. ROSIE v0.1 has none. |
| `DOCUMENTATION_PUBLISHERS` | Local Git repository, uncommitted drafts | Where generated documents go. |
| `DEFAULT_DOCUMENT_FORMAT` | `Markdown` | Format for generated documents. |
| `SUPPORTED_DOCUMENT_FORMATS` | Markdown export; six ingestion formats | Formats ROSIE can read and write. |
| `DEFAULT_USER_LEVEL` | Accessible technical language | How technical answers should be. |
| `ACTION_POLICY` | Advisory only | What ROSIE may do. |
| `APPROVAL_POLICY` | No infrastructure actions; publishing creates drafts only | What needs approval. |
| `RESTRICTED_SYSTEMS` | All infrastructure systems | Systems ROSIE must not act on. |
| `SENSITIVE_DATA_POLICY` | Do not request or store secrets | How to treat secrets. |
| `ESCALATION_CONFIGURATION` | Contact the responsible operator | Who to escalate to. |

These describe ROSIE's situation to the model; they do not grant or restrict anything. ROSIE v0.1 has no infrastructure access regardless of these values.

To change the prompt itself, edit `docs/rosie/system-prompt.md`. The app mounts it read-only and re-reads it for every question. `SYSTEM_PROMPT_PATH` can point to another file, but it must be a path inside the container.

## Hardware Status

These affect only `GET /api/health/gpu` and the hardware footer in the chat page, which display data written by the optional [thermal controller](operations/p4-thermal-controller.md).

| Setting | Default | Description |
| --- | --- | --- |
| `ROSIE_GPU_STATUS_PATH` | `/run/p4-thermal/status.json` | Status file to read, as seen inside the container. |
| `ROSIE_GPU_STATUS_MAX_AGE` | `30` | Seconds after which the status is shown as out of date. |

### Thermal Controller

`p4-thermal.py` takes command-line flags, not `.env` settings. To change them, override `ExecStart` with `sudo systemctl edit p4-thermal.service`; the [thermal controller guide](operations/p4-thermal-controller.md#5-tune-thresholds) has an example.

| Flag | Default | Description |
| --- | --- | --- |
| `--interval` | `5` | Seconds between readings. |
| `--full-above` | `84` | Switch fans to Full at or above this GPU temperature (°C). |
| `--optimal-below` | `55` | Allow Optimal fan mode at or below this temperature. Must be lower than `--full-above`. |
| `--cool-hold` | `120` | Seconds the GPU must stay at or below `--optimal-below` before returning to Optimal. |
| `--warn-temp` | `80` | Status shows "running hot" at or above this temperature. |
| `--critical-temp` | `85` | Status shows critical at or above this temperature. |
| `--max-failures` | `3` | Consecutive failed GPU readings before forcing Full. |
| `--reassert` | `60` | Seconds between re-sending the current fan mode to the BMC. |
| `--status-path` | `/run/p4-thermal/status.json` | Where to write the status file. |
| `--dry-run` | off | Read and report, but never change fan mode. |
| `--once` | off | Run one cycle, print the status, and exit. |

## Fixed Container Settings

`docker-compose.yml` sets these explicitly, so values in `.env` do not affect the containers. They are listed for local development, where they can be set.

| Setting | Compose value | Local default |
| --- | --- | --- |
| `QDRANT_URL` | `http://qdrant:6333` | `http://localhost:6333` |
| `DOCS_PATH` | `/app/knowledge` (host `./knowledge`) | `./knowledge` |
| `REPOSITORY_PATH` | `/app/published-runbooks` (host `RUNBOOK_PUBLISH_PATH`) | `./docs/rosie/generated-runbooks` |
| `AUDIT_LOG_PATH` | `/app/data/audit.jsonl` | `./data/audit.jsonl` |

`APP_NAME` (default `ROSIE`) sets only the API title shown at `/docs`.

### Ports

The ROSIE web page and API are published on port `8001` on all host interfaces. To change the port, edit the `ports` entry of the `app` service in `docker-compose.yml`, and update `SOURCE_SYNC_API_URL` if you use the host timer. Qdrant is published on `127.0.0.1:6333`, reachable only from the host; the llama.cpp servers are not published.

ROSIE has no authentication. Anyone who can reach port 8001 can ask questions, upload documents, start syncs, and write runbook drafts. Allow the port only from trusted networks.
