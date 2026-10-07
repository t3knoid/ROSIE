# Model Configurations

ROSIE uses Ollama for chat completion and embeddings. `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, and `OLLAMA_EMBEDDING_MODEL` are configurable. Defaults are `qwen2.5:7b` for chat and `nomic-embed-text` for embeddings; keep the roles separate because chat models are not necessarily suitable embedding models.

The Compose setup persists Ollama's model cache. Pull both configured models into the Ollama service before ingesting documents or using chat. `RELEVANCE_THRESHOLD` controls the minimum Qdrant cosine similarity returned as evidence. Model quality, memory use, and response time depend on the selected models and host hardware.
