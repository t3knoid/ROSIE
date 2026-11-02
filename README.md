# ROSIE

ROSIE (Root-cause Observation, SRE Incident Examiner) is a documentation-aware operations assistant. Version 0.1 is deliberately documentation-only: it indexes local operational knowledge, retrieves evidence, guides investigations, identifies runbook gaps, and drafts structured runbooks for review. It does not connect to or change infrastructure.

## MVP

- FastAPI API and a small browser-based chat interface
- LangGraph investigation flow backed by llama.cpp (Llama GGUF by default)
- Qdrant vector storage and semantic search
- Markdown, HTML, PDF, DOCX, ODT, and plain-text ingestion
- Canonical runbook model, Markdown export, and local Git-repository publishing
- JSON Lines audit records for questions, evidence sources, and documentation operations

## Run With Docker Compose

Requires Docker Compose, NVIDIA Container Toolkit, enough memory and disk for the selected GGUF models, and compatible chat and embedding model files in `./models` (configurable with `LLAMA_MODELS_PATH`). This Compose configuration uses llama.cpp's CUDA 12 server image and passes the NVIDIA GPU to both model servers. It suits the installed Tesla P4; do not use the CUDA 13 image with this Pascal-generation card. The default filenames, model aliases, and GPU-layer setting are in `.env.example`.

```sh
cp .env.example .env
```

The default chat file is the Q4_K_M quantization from [bartowski's Llama 3.2 3B Instruct GGUF repository](https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF) (about 2.02 GB). The default embedding file is from [Nomic's nomic-embed-text-v1.5 GGUF repository](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5-GGUF) (about 84 MB, Apache-2.0). Review each model card and license; the chat model is subject to Meta's Llama 3.2 license terms.

Download the exact files configured in `.env.example` into `./models` with `curl`:

```sh
mkdir -p models
curl --location --fail --retry 3 --continue-at - \
	'https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main/Llama-3.2-3B-Instruct-Q4_K_M.gguf?download=true' \
	--output models/Llama-3.2-3B-Instruct-Q4_K_M.gguf
curl --location --fail --retry 3 --continue-at - \
	'https://huggingface.co/nomic-ai/nomic-embed-text-v1.5-GGUF/resolve/main/nomic-embed-text-v1.5.Q4_K_M.gguf?download=true' \
	--output models/nomic-embed-text-v1.5.Q4_K_M.gguf
```

For a different model directory, change `LLAMA_MODELS_PATH` in `.env` and update the download destinations to match; for different compatible files, change `LLAMA_CHAT_MODEL_FILE` and `LLAMA_EMBEDDING_MODEL_FILE` as well. The embedding model must support llama.cpp embedding mode.

The P4 has 8 GB of VRAM. `LLAMA_PARALLEL=1` limits each llama.cpp server to one active slot to reduce peak GPU memory use; raise it only if the GPU has adequate headroom. `LLAMA_N_GPU_LAYERS=99` asks llama.cpp to offload all model layers; if a server cannot allocate enough VRAM, lower this value in `.env` to offload fewer layers and leave the rest on the CPU. Check the [llama.cpp Docker guide](https://github.com/ggml-org/llama.cpp/blob/master/docs/docker.md) and [NVIDIA Container Toolkit installation guide](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) if Docker cannot see the GPU.

```sh
sudo docker compose up --build
```

After startup, inspect the llama.cpp logs for CUDA detection and layer offload, then check GPU memory while ROSIE is generating a response:

```sh
sudo docker compose logs llama-chat llama-embeddings
nvidia-smi
```

Open `http://localhost:8001` on the host. From another device on the same LAN, use `http://<host-lan-ip>:8001`; find the current host address with `ip -brief address show` and use the address on its active physical interface, not `127.0.0.1` or a Docker bridge. The API reference is at `/docs`. ROSIE's web/API port is published on host network interfaces; Qdrant and both llama.cpp servers are only reachable inside the Compose network. Allow TCP port 8001 through the host firewall only on trusted networks.

**Configured HTTP sources:** `DOCUMENTATION_SOURCE_URL` and `RUNBOOK_SOURCE_URL` in `.env` define the remote documentation and runbook index pages. In the chat page, click **Sync sources**, or call **POST /api/ingest/sources**, to fetch those HTTPS pages and bounded same-origin HTML links and index them. Sync is operator-triggered; no background crawl runs. Crawl limits and timeouts are configurable, with defaults of 100 pages per source and 2 MB per page. The chat page remembers the last successful sync time in that browser.

**Optional local ingestion:** if you also have local files, put documents under `knowledge/` and runbooks under `knowledge/runbooks/`, then use **POST /api/ingest/local**. Individual files can instead be uploaded through **POST /api/ingest** with `kind=document` or `kind=runbook`. These local options are separate from the configured HTTP source sync.

Both llama.cpp servers must be running with their configured models available before chat, ingestion, or runbook generation can use inference and embeddings. `RELEVANCE_THRESHOLD` (default `0.35`) controls the minimum Qdrant cosine score returned as evidence.

For faster chat responses on smaller GPUs, ROSIE defaults to at most four evidence passages (`CHAT_EVIDENCE_LIMIT`) and 512 generated tokens (`CHAT_MAX_OUTPUT_TOKENS`). Raise these `.env` values for more context or longer answers, knowing that more passages increase prompt processing time and a higher output limit allows longer generation.

## Local Development

Python 3.12 or newer is required.

```sh
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
uvicorn rosie.main:app --reload --host 0.0.0.0 --port 8001
```

For local development, ROSIE defaults to llama.cpp chat at `http://localhost:8080/v1`, embeddings at `http://localhost:8081/v1`, and Qdrant at `http://localhost:6333`. Start llama.cpp servers with compatible chat and embedding GGUFs before using inference or ingestion. Inside Compose, the app uses the `llama-chat`, `llama-embeddings`, and `qdrant` service names on the private Compose network. The settings in `rosie/config.py` are environment configurable.

## API

- `POST /api/ingest` and `POST /api/ingest/local`: index documents
- `POST /api/ingest/sources`: fetch and index configured documentation and runbook pages
- `GET /api/search?q=...&kind=document|runbook`: retrieve evidence
- `POST /api/chat`: investigate a question using indexed documentation
- `GET /api/runbooks/gap?q=...`: check for a matching runbook
- `POST /api/runbooks/draft`: generate a canonical runbook draft
- `POST /api/runbooks/export`: render a runbook as Markdown
- `POST /api/runbooks/publish`: write a new Markdown draft under the configured repository path; review and commit with Git yourself

## Tests

```sh
pip install -e '.[dev]'
pytest
```

See [docs/rosie](docs/rosie/README.md) for the architecture, safety principles, and development notes, including the [Tesla P4 GPU operations guide](docs/rosie/gpu-acceleration.md).
