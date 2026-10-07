# ROSIE Workspace Instructions

- Keep v0.1 documentation-first. Do not add infrastructure connectors or execute infrastructure changes.
- Ground operational answers in indexed evidence, cite source names, and state uncertainty when evidence is missing.
- Keep runbooks in the canonical `Runbook` model and render Markdown through `rosie.runbooks`; do not generate Markdown directly from workflow code.
- Treat generated runbooks as drafts. Publishing writes to a checked-out repository but does not commit changes.
- Keep Qdrant, Ollama, paths, and model names configurable through environment-backed settings.
- Add focused tests for parsing, evidence handling, runbook rendering, and publishing path safety.
