# Architecture

ROSIE runs as four Docker Compose services, with two optional host services.

```text
                      Browser (chat page)  /  API clients
                                 |
                                 v  port 8001
 +------------------------ ROSIE app (FastAPI) ------------------------+
 |  LangGraph investigation   web crawler     document parsers         |
 |  runbook drafting          audit log       publisher                |
 +---+--------------------+---------------+--------------+-------------+
     |                    |               |              |
     v                    v               v              v
 llama-chat         llama-embeddings    Qdrant      RUNBOOK_PUBLISH_PATH
 (chat GGUF)        (embedding GGUF)   (passages)   (Markdown drafts)
     \___________________/
       shared NVIDIA GPU

 Host (optional):
   rosie-source-sync.timer --> POST /api/ingest/sources (scheduled re-sync)
   p4-thermal.service ------> /run/p4-thermal/status.json --> GET /api/health/gpu (live)
                                                          --> GET /api/health/system (GPU model, VRAM size)
```

## Components

| Component | Technology | Role |
| --- | --- | --- |
| ROSIE app | Python 3.12, FastAPI, LangGraph | Web page, REST API, crawling, parsing, investigation workflow, runbook rendering, publishing, audit log. |
| `llama-chat` | llama.cpp server (CUDA 12), GGUF chat model | Answers questions and drafts runbooks through an OpenAI-compatible API. |
| `llama-embeddings` | llama.cpp server (CUDA 12), GGUF embedding model | Turns passages and questions into vectors. |
| Qdrant | Qdrant 1.12 | Stores passages with their vectors and `source` and `kind` (`document` or `runbook`). |
| Source sync timer | systemd timer + `rosie.source_sync` | Optional. Calls the sync endpoint on a schedule. See [source sync](operations/source-sync.md). |
| Thermal controller | systemd service + `p4-thermal.py` | Optional. Controls Supermicro fan modes from the GPU temperature and writes a status file. See the [thermal controller guide](operations/p4-thermal-controller.md). |

Settings for all of these are described in [configuration](configuration.md).

## Data Flows

**Indexing.** Text is extracted from web pages, local files, or uploads, leaving out site navigation, headers, and footers. It is split into passages at headings, with long sections split further (up to about 1,200 characters); each passage starts with its page title and section. Passages are embedded by `llama-embeddings` and stored in Qdrant. Each passage keeps its source (URL or file name) and kind. Re-indexing a source replaces its passages, and passages whose text has not changed are not re-embedded.

**Source sync.** At startup, on request, and on the optional timer, the app crawls the configured documentation site and runbook index (same-origin HTTPS HTML only, with page and size limits) and indexes the pages. Pages no longer on the site are removed from the index, but only after a complete crawl: one that stayed within the page limit and whose only failures were 404 or 410 responses. Chat is unavailable until one sync finishes without errors. Readiness and the sync lock are held in the app process, so the app must run as a single Uvicorn worker.

**Investigation.** For each question, the app retrieves the best-matching passages and searches runbooks separately. The closest runbook's text is added to the evidence in page order, up to about 4,000 characters plus the passage the search matched, so the model sees its steps and commands. When the next runbook scores within 0.03, its best passage is added too. The model is told which runbooks they are. It sends the system prompt, the evidence (grouped by source), and the question to `llama-chat`, then renders the Markdown answer to sanitized HTML. Each question is independent; there is no conversation memory.

**Runbooks.** Drafts are generated as structured data, rendered to Markdown only by the exporter, and written by the publisher as new files. See [runbooks](runbooks.md).

**Audit.** Ingestion, searches, questions, gap checks, and runbook operations are appended to a JSON Lines audit log.

## Trust Boundaries

- ROSIE has no infrastructure credentials or connectors. It cannot observe or change live systems.
- Indexed documents, web pages, and pasted output are treated as evidence, not instructions. The system prompt tells the model not to follow instructions in them; this reduces, but does not eliminate, the risk from a malicious document.
- Model output is advisory. Generated runbooks are drafts until a person reviews them.
- Publishing writes a new file only. It never overwrites, stages, commits, or pushes.
- The app can write only to the publish directory and its audit log volume. Documentation and local knowledge are mounted read-only.
- The API has no authentication. Anyone who can reach port 8001 can query, upload, sync, and publish. Run it only on trusted networks.
- The llama.cpp servers are reachable only inside the Compose network. Qdrant is also published on `127.0.0.1:6333` for host access.
- The GPU status endpoint only reads a file. ROSIE never runs `nvidia-smi` or `ipmitool`.

## Not Implemented in v0.1

- Observability integrations (Grafana, Prometheus, Loki) and infrastructure integrations (Docker, Kubernetes, Proxmox, VMware, network devices).
- Documentation platforms (Confluence, Wiki.js, BookStack, MediaWiki) and Git hosting workflows.
- Any infrastructure action.
- Authentication, roles, and multi-user audit identity.

See the [roadmap](roadmap.md).
