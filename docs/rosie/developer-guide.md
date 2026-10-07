# Developer Guide

## Requirements

- Python 3.12+
- Docker Compose for the complete local stack
- An Ollama-compatible host and sufficient resources for Qwen

## Development

Install the project and test extras with `pip install -e '.[dev]'`. Run the API with `uvicorn rosie.main:app --reload` after setting service URLs in the environment. Run tests with `pytest`.

For Compose, start the services with `docker compose up --build`, pull the chat and embedding models with `docker compose exec ollama ollama pull qwen2.5:7b` and `docker compose exec ollama ollama pull nomic-embed-text`, then use `http://localhost:8001`. ROSIE, Qdrant, and Ollama ports are published only on host loopback. Store source material under `knowledge/`; use `knowledge/runbooks/` for runbooks.

For local development outside Compose, ROSIE uses `http://localhost:11434` for Ollama and `http://localhost:6333` for Qdrant by default. Start ROSIE with `uvicorn rosie.main:app --reload --host 127.0.0.1 --port 8001`.

## Change Guidelines

Keep integrations behind small adapters, do not add infrastructure actions to v0.1, and add focused tests for changes to ingestion, retrieval metadata, runbook structure, publishing, or audit events.
