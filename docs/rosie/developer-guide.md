# Developer Guide

## Requirements

- Python 3.12+
- Docker Compose for the complete local stack
- An Ollama-compatible host and sufficient resources for Qwen

## Development

Install the project and test extras with `pip install -e '.[dev]'`. Run the API with `uvicorn rosie.main:app --reload` after setting service URLs in the environment. Run tests with `pytest`.

For Compose, start the services with `docker compose up --build`, pull the model with `docker compose exec ollama ollama pull qwen2.5:7b`, then use `http://localhost:8000`. Store source material under `knowledge/`; use `knowledge/runbooks/` for runbooks.

## Change Guidelines

Keep integrations behind small adapters, do not add infrastructure actions to v0.1, and add focused tests for changes to ingestion, retrieval metadata, runbook structure, publishing, or audit events.
