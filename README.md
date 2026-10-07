# ROSIE

ROSIE (Root-cause Observation, Simulation & Incident Examiner) is a documentation-aware operations assistant. Version 0.1 is deliberately documentation-only: it indexes local operational knowledge, retrieves evidence, guides investigations, identifies runbook gaps, and drafts structured runbooks for review. It does not connect to or change infrastructure.

## MVP

- FastAPI API and a small browser-based chat interface
- LangGraph investigation flow backed by Ollama (Qwen by default)
- Qdrant vector storage and semantic search
- Markdown, HTML, PDF, DOCX, ODT, and plain-text ingestion
- Canonical runbook model, Markdown export, and local Git-repository publishing
- JSON Lines audit records for questions, evidence sources, and documentation operations

## Run With Docker Compose

Requires Docker Compose and enough memory and disk for the selected Ollama model.

```sh
cp .env.example .env
docker compose up --build
```

In another terminal, download the configured Qwen model:

```sh
docker compose exec ollama ollama pull qwen2.5:7b
docker compose exec ollama ollama pull nomic-embed-text
```

Open `http://localhost:8001` on the host, or `http://<host-ip>:8001` from another device on the LAN (for example, `http://192.168.20.101:8001`). The API reference is at `/docs`. ROSIE's web/API port is published on host network interfaces; Qdrant and Ollama remain bound to loopback. Allow TCP port 8001 through the host firewall only on trusted networks.

Put source documentation under `knowledge/`, with runbooks under `knowledge/runbooks/`, then use **POST /api/ingest/local** to index it. Individual files can also be uploaded through **POST /api/ingest** with `kind=document` or `kind=runbook`. Ollama must be running with both configured models available before chat, ingestion, or runbook generation can use embeddings/model inference. `RELEVANCE_THRESHOLD` (default `0.35`) controls the minimum Qdrant cosine score returned as evidence.

## Local Development

Python 3.12 or newer is required.

```sh
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
uvicorn rosie.main:app --reload --host 0.0.0.0 --port 8001
```

For local development, ROSIE defaults to Ollama at `http://localhost:11434` and Qdrant at `http://localhost:6333`. Inside Compose, the app uses the `ollama` and `qdrant` service names on the private Compose network. The settings in `rosie/config.py` are environment configurable.

## API

- `POST /api/ingest` and `POST /api/ingest/local`: index documents
- `GET /api/search?q=...&kind=document|runbook`: retrieve evidence
- `POST /api/chat`: investigate a question using indexed documentation
- `GET /api/runbooks/gap?q=...`: check for a matching runbook
- `POST /api/runbooks/draft`: generate a canonical runbook draft
- `POST /api/runbooks/export`: render a runbook as Markdown
- `POST /api/runbooks/publish`: write a new Markdown draft under the configured repository path; review and commit with Git yourself

## Tests

```sh
pip install -e '.[dev]'
pytest
```

See [docs/rosie](docs/rosie/README.md) for the architecture, safety principles, and development notes.
