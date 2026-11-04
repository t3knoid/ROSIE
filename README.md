# ROSIE

ROSIE (Root-cause Observation, SRE Incident Examiner) is a documentation-aware operations assistant. It indexes your operational documentation and runbooks, answers questions from them with sources, identifies runbook gaps, and drafts structured runbooks for review. Version 0.1 is deliberately documentation-only: it does not connect to or change infrastructure.

- Browser chat and REST API (FastAPI), with a LangGraph investigation workflow
- Local llama.cpp chat and embedding models (GGUF) on an NVIDIA GPU, and Qdrant for search
- Indexes a documentation website and runbook index, local files, and uploads (Markdown, HTML, PDF, DOCX, ODT, plain text)
- Structured runbook drafts, Markdown export, and uncommitted drafts written to a local Git checkout
- JSON Lines audit log of questions, evidence, and documentation operations

## Quick Start

### 1. Prerequisites

- Linux with Docker Compose v2, an NVIDIA GPU, and the NVIDIA Container Toolkit. The [GPU guide](docs/rosie/operations/gpu-acceleration.md) covers setup and checks; it uses a Tesla P4 with 8 GB of VRAM. The Compose file uses llama.cpp's CUDA 12 image, which supports Pascal cards like the P4; do not switch to the CUDA 13 image on Pascal.
- About 2.5 GB of disk for the default models.

### 2. Download the Models

The default chat model is the Q4_K_M file from [bartowski's Llama 3.2 3B Instruct GGUF repository](https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF) (about 2.02 GB). The default embedding model is from [Nomic's nomic-embed-text-v1.5 GGUF repository](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5-GGUF) (about 84 MB, Apache-2.0). Review each model card and license; the chat model is subject to Meta's Llama 3.2 license.

```sh
mkdir -p models
curl --location --fail --retry 3 --continue-at - \
	'https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main/Llama-3.2-3B-Instruct-Q4_K_M.gguf?download=true' \
	--output models/Llama-3.2-3B-Instruct-Q4_K_M.gguf
curl --location --fail --retry 3 --continue-at - \
	'https://huggingface.co/nomic-ai/nomic-embed-text-v1.5-GGUF/resolve/main/nomic-embed-text-v1.5.Q4_K_M.gguf?download=true' \
	--output models/nomic-embed-text-v1.5.Q4_K_M.gguf
```

To use other models or another directory, see [models and GPU settings](docs/rosie/configuration.md#models-and-gpu).

### 3. Configure

```sh
cp .env.example .env
```

At minimum, set `DOCUMENTATION_SOURCE_URL` and `RUNBOOK_SOURCE_URL` to your documentation site and runbook index page. The [configuration reference](docs/rosie/configuration.md) describes every setting.

### 4. Start

```sh
sudo docker compose up -d --build
sudo docker compose logs -f llama-chat llama-embeddings
```

Wait until both llama.cpp servers report that their models are loaded and offloaded to the GPU.

### 5. Use

Open `http://localhost:8001`, or `http://<host-ip>:8001` from another device on the LAN. ROSIE syncs the configured sources on startup; the prompt is enabled when the first sync finishes without errors. If it stays disabled, see [source sync](docs/rosie/operations/source-sync.md#readiness).

To add local files, put documents under `knowledge/` and runbooks under `knowledge/runbooks/`, then run `curl -X POST http://localhost:8001/api/ingest/local`. To upload a single file, use `POST /api/ingest`.

The API reference is at `http://localhost:8001/docs`.

**Security:** ROSIE has no authentication, and port 8001 is published on all host interfaces. Anyone who can reach it can query, upload, sync, and write runbook drafts. Allow the port through the host firewall only from trusted networks.

## Documentation

The [documentation index](docs/rosie/README.md) lists every guide. Where to start depends on what you want to do.

### Using ROSIE

1. Follow the [Quick Start](#quick-start) above.
2. Read [Configuration](docs/rosie/configuration.md) to point ROSIE at your own documentation and describe your environment to it.
3. Read [Source sync](docs/rosie/operations/source-sync.md) to understand when content is indexed and why the prompt can stay disabled.
4. Read [Runbooks](docs/rosie/runbooks.md) to draft, export, and publish runbooks.
5. If something goes wrong, check [Troubleshooting](docs/rosie/operations/troubleshooting.md).

### Developing ROSIE

1. Read the [Overview](docs/rosie/overview.md) and [Architecture](docs/rosie/architecture.md) to understand what ROSIE is for, how it fits together, and why v0.1 stays documentation-only.
2. Set up a local environment and run the tests with the [Developer guide](docs/rosie/developer-guide.md) (`pip install -e '.[dev]' && pytest`). It also describes the code layout and the change guidelines to follow.
3. Check the [Roadmap](docs/rosie/roadmap.md) to see what is planned, and the [Changelog](docs/rosie/changelog.md) for recent changes. Add an entry to the changelog for any user-visible change.
4. If you add or change a setting, document it in [Configuration](docs/rosie/configuration.md) and `.env.example`.
