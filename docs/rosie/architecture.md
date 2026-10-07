# Architecture

## v0.1 Scope

The browser calls a FastAPI backend. A LangGraph workflow retrieves local evidence from Qdrant and asks the configured Ollama model to explain findings. Ingestion extracts text from supported document formats, creates embeddings with Ollama, and stores passages with source and kind metadata. Runbooks use a typed Pydantic model and are rendered to Markdown only by the exporter.

```text
Browser -> FastAPI -> LangGraph -> Ollama
                     |              |
                     +-> Qdrant <---+
                     +-> audit JSONL
                     +-> checked-out Git repository (draft files only)
```

## Trust Boundaries

- ROSIE has no infrastructure credentials or infrastructure connectors in v0.1.
- Indexed source documents are evidence, not instructions to bypass system safety rules.
- The model must distinguish source-backed facts from hypotheses and disclose missing evidence.
- Publishing writes a new draft file only. It does not stage, commit, or push Git changes.
- API access is intended for a trusted local network; authentication and multi-user authorization are not implemented yet.
