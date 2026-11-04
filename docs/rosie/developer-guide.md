# Developer Guide

## Requirements

- Python 3.12 or newer
- llama.cpp chat and embedding servers with compatible GGUF models, and a Qdrant instance; the easiest way is the Compose stack
- Docker Compose with the NVIDIA Container Toolkit for the full stack (see the [GPU guide](operations/gpu-acceleration.md))

## Local Setup

```sh
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
pytest
```

To run the API outside Docker, start the two llama.cpp servers and Qdrant, then:

```sh
uvicorn rosie.main:app --reload --host 0.0.0.0 --port 8001
```

Outside Compose, ROSIE expects llama.cpp chat at `http://localhost:8080/v1`, embeddings at `http://localhost:8081/v1`, and Qdrant at `http://localhost:6333`, and reads `.env` from the working directory. The Compose stack publishes Qdrant on `127.0.0.1:6333`, so a local app can share it; the llama.cpp servers are not published. Settings are listed in [configuration](configuration.md).

## Code Layout

| Module | Responsibility |
| --- | --- |
| `rosie/main.py` | FastAPI app, endpoints, startup sync, readiness |
| `rosie/config.py` | Environment-backed settings |
| `rosie/models.py` | API and `Runbook` models |
| `rosie/workflow.py` | LangGraph investigation, prompt loading, runbook drafting |
| `rosie/knowledge.py` | Embedding, Qdrant storage, and search |
| `rosie/documents.py` | Text extraction and chunking |
| `rosie/web_sources.py` | Bounded same-origin crawler |
| `rosie/rendering.py` | Markdown to sanitized HTML |
| `rosie/runbooks.py`, `rosie/publisher.py` | Runbook Markdown rendering and file publishing |
| `rosie/gpu_status.py` | Read-only GPU status endpoint |
| `rosie/source_sync.py` | Host timer worker |
| `rosie/static/index.html` | Chat page |
| `deploy/host/` | Optional systemd units and the thermal controller |

The API reference is generated from the code at `/docs`. When adding an endpoint, give it a summary, a docstring, a tag, and a response model; a test checks this.

## Sync and Readiness Internals

Readiness (`app.state.source_sync`) and the sync lock live in the app process. Keep the single-worker Uvicorn deployment; multiple workers would each sync on startup and keep separate readiness. Operator-facing behavior is described in [source sync](operations/source-sync.md).

## Change Guidelines

- Keep v0.1 documentation-only. Do not add infrastructure actions or connectors.
- Keep integrations behind small adapters.
- Keep runbooks in the `Runbook` model and render Markdown only through `rosie.runbooks`.
- Keep service URLs, paths, and model names configurable through `rosie/config.py`, and document new settings in [configuration](configuration.md) and `.env.example`.
- Add focused tests for changes to ingestion, retrieval metadata, runbook structure, publishing, rendering, or audit events.
- Record user-visible changes in the [changelog](changelog.md).
