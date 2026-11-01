# Developer Guide

## Requirements

- Python 3.12+
- Docker Compose for the complete local stack
- llama.cpp-compatible chat and embedding GGUF files and sufficient host resources

## Development

Install the project and test extras with `pip install -e '.[dev]'`. Run the API with `uvicorn rosie.main:app --reload` after setting service URLs in the environment. Run tests with `pytest`.

For Compose, put compatible chat and embedding GGUF files in the model directory (default `./models`) and set their filenames in `.env` if they differ from `.env.example`; then start services with `docker compose up --build` and use `http://localhost:8001` or `http://<host-ip>:8001` from another LAN device. ROSIE is published on host network interfaces; Qdrant and both llama.cpp servers are reachable only inside the Compose network. Restrict TCP port 8001 in the host firewall to trusted networks. Store source material under `knowledge/`; use `knowledge/runbooks/` for runbooks. In the chat page, click **Sync sources** to fetch and index configured web sources on demand; the last successful sync time is remembered in that browser. The equivalent API endpoint is `POST /api/ingest/sources`.

For local development outside Compose, ROSIE uses `http://localhost:8080/v1` for llama.cpp chat, `http://localhost:8081/v1` for embeddings, and `http://localhost:6333` for Qdrant by default. Start the two llama.cpp servers separately with the selected GGUFs. To make the page available on the LAN, start ROSIE with `uvicorn rosie.main:app --reload --host 0.0.0.0 --port 8001`. Restrict access with the host firewall.

## Change Guidelines

Keep integrations behind small adapters, do not add infrastructure actions to v0.1, and add focused tests for changes to ingestion, retrieval metadata, runbook structure, publishing, or audit events.
