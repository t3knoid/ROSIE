# Lessons Learned

## Initial Release

- Empty retrieval is a meaningful result: responses should disclose that local documentation did not support the answer.
- Runbooks are structured operational data first; Markdown is an export format, not the source of truth.
- Model output is a draft. Review and Git commit remain operator responsibilities.
- Ingestion and semantic search require both a reachable Ollama model and Qdrant, so failures should be surfaced as service availability issues rather than fabricated answers.
