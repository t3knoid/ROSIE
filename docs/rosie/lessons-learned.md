# Lessons Learned

## Initial Release

- Empty retrieval is a meaningful result: responses should disclose that local documentation did not support the answer.
- Runbooks are structured operational data first; Markdown is an export format, not the source of truth.
- Model output is a draft. Review and Git commit remain operator responsibilities.
- Ingestion and semantic search require a reachable llama.cpp embedding model and Qdrant; chat and runbook drafting also require the llama.cpp chat model. Surface service failures rather than fabricating answers.
