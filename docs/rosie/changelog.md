# Changelog

## Unreleased

### Added

- Source sync runs automatically at startup and retries until it succeeds. Chat is unavailable until then, and the sync status is shared by all browsers.
- Optional host systemd timer for scheduled source syncs, configured with `SOURCE_SYNC_*` settings.
- Optional Tesla P4 thermal controller host service, with GPU model, VRAM, temperature, and fan status shown in a footer on the chat page and at `GET /api/health/gpu`.
- `RUNBOOK_PUBLISH_PATH` chooses the host directory for published runbooks.
- All app settings in `.env`, including the organization and prompt context settings, now reach the app container.
- Swagger documentation at `/docs` with descriptions, examples, error codes, and typed responses for every endpoint.
- URLs in answers, including URLs in inline code, are clickable.
- Pressing Enter in the prompt sends the question; Shift+Enter adds a new line.
- A [configuration reference](configuration.md), plus [source sync](operations/source-sync.md) and [troubleshooting](operations/troubleshooting.md) guides.

### Changed

- Replaced Ollama with separate llama.cpp chat and embedding servers using local GGUF models. The default chat model is Llama 3.2 3B Instruct.
- Shortened the system prompt and reduced evidence per question from four passages to two, for faster answers.
- Evidence lists each source once, with all its kinds; identical passages are sent to the model once.
- Pages found by both the documentation and runbook crawls are stored once, as runbooks; re-syncing removes conflicting older entries.
- The chat page uses its full width; hardware status moved from a sidebar to a compact footer.
- The app container mounts `docs/rosie` read-only and can write only to the publish directory.
- Reorganized the documentation; the original requirements draft is archived.

### Fixed

- Exporting a runbook whose title contains non-Latin-1 characters, quotes, or line breaks no longer fails.
- Large uploads no longer block other requests while they are processed.
- Unchanged passages are not re-embedded or duplicated when a source is re-indexed.
- Passages no longer start in the middle of a word. Previously, the overlap between passages could cut names such as `deploy_truenas_vms.yml` to `enas_vms.yml`, and answers repeated the fragment.

## 0.1.0 - Initial MVP

- Added a documentation-only investigation workflow with FastAPI, LangGraph, Ollama, and Qdrant.
- Added supported document ingestion, semantic search, runbook gap assessment, structured runbook drafts, Markdown export, and local repository publishing.
- Added a browser chat, Docker Compose setup, and JSONL audit events.
