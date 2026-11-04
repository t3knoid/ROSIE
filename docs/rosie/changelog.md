# Changelog

## Unreleased

- Added mandatory startup source syncing with retries, shared sync status, and prompt/API readiness gating until the initial sync succeeds.
- Added an opt-in host systemd source-sync timer with environment-configurable enablement, interval, API URL, and timeout; partial failures are reported in the journal.
- Replaced Ollama with separate llama.cpp chat and embedding servers using local GGUF models.

## 0.1.0 - Initial MVP

- Added a documentation-only investigation workflow with FastAPI, LangGraph, Ollama, and Qdrant.
- Added supported document ingestion, semantic search, runbook gap assessment, structured runbook drafts, Markdown export, and local repository publishing.
- Added a browser chat, Docker Compose setup, and JSONL audit events.
