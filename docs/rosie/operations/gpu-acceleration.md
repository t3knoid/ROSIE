# NVIDIA GPU Acceleration with llama.cpp and ROSIE

This guide covers the Linux Docker Compose deployment of ROSIE using an NVIDIA GPU. The example host has a Tesla P4 with 8 GB of VRAM and driver 580.178.04. Commands below assume Ubuntu or Debian, Docker Compose v2, and the repository root as the current directory. For other Linux distributions, use the matching package-manager instructions in NVIDIA's [Container Toolkit installation guide](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html).

## How ROSIE Uses the GPU

ROSIE does not run inference inside the Python API container. Compose starts two llama.cpp servers, and the ROSIE app calls them over the private Compose network:

| Service | ROSIE workload | Compose endpoint | Model |
| --- | --- | --- | --- |
| `llama-chat` | Chat investigations and runbook drafts | `http://llama-chat:8080/v1` | Chat GGUF |
| `llama-embeddings` | Document ingestion and semantic search | `http://llama-embeddings:8081/v1` | Embedding GGUF |

Both services use `ghcr.io/ggml-org/llama.cpp:server-cuda`, receive an NVIDIA GPU reservation, and read models from `LLAMA_MODELS_PATH`. They share the same physical GPU; the reservation does not divide or dedicate VRAM between them. ROSIE sets `LLAMA_PARALLEL=1` by default, limiting each server to one active slot to reduce peak GPU memory use. Raising this setting increases concurrency and memory demand. The API and Qdrant do not use the GPU. The llama.cpp server ports are not published to the host by default.

## Memory and Context Sizing

The Tesla P4 has 8 GB of VRAM. ROSIE's default Llama 3.2 3B Q4_K_M chat weights occupy about 2.02 GB; the context cache and CUDA runtime need additional memory. The embedding model is much smaller but adds its own GPU allocation (allow a few hundred MB). Both servers share the same card, and available memory also depends on other GPU processes and runtime settings. The single-slot default avoids multiplying context-cache allocation across several simultaneous requests.

Keep the chat context as small as the workload allows to avoid exhausting VRAM. ROSIE sets `LLAMA_CTX_SIZE=10240` by default, corresponding to llama.cpp's `-c 10240` option. The context must hold the system prompt, the evidence passages (`CHAT_EVIDENCE_LIMIT`), the question, and the answer (up to `CHAT_MAX_OUTPUT_TOKENS`); with the defaults this uses well under half of it, leaving room to raise those settings. If the P4 reports CUDA out-of-memory, reduce `LLAMA_CTX_SIZE` and/or `LLAMA_N_GPU_LAYERS` as described in [Tune VRAM Use](#8-tune-vram-use).

## CUDA Architecture Compatibility

The Tesla P4 is a Pascal GPU (compute capability 6.1). ROSIE uses llama.cpp's CUDA 12 `server-cuda` image, which supports this generation; inference speed will be modest compared with newer GPUs. Very recent CUDA releases, including CUDA 13, drop Pascal support in relevant libraries. Do not switch this host to `server-cuda13`.

If llama.cpp logs an error such as `no kernel image available`, use a llama.cpp image built with CUDA 12.x and Pascal (`sm_61`) support. The `CUDA Version` printed by host `nvidia-smi` is the maximum CUDA version supported by the driver; it does not mean that the host CUDA toolkit must be installed. For this Docker deployment, the host needs the NVIDIA driver and Container Toolkit; the CUDA runtime and llama.cpp backend are supplied by the container image. A newer driver such as 580.178.04 can run CUDA 12 workloads.

## 1. Check the Host Driver

Run this on the Linux host before changing Docker configuration:

```sh
nvidia-smi
```

Confirm that the Tesla P4 appears, the driver is loaded, and the expected 8 GB of memory is visible. If this command fails, resolve the host driver issue before proceeding; Docker cannot pass through a GPU that the host cannot see.

If the driver is not installed or `nvidia-smi` cannot see the card on Ubuntu, install the recommended NVIDIA driver and reboot:

```sh
sudo ubuntu-drivers install
sudo reboot
```

After the host returns, rerun `nvidia-smi`. If it lists the Tesla P4, skip driver installation and continue to step 2.

## 2. Install the NVIDIA Container Toolkit (Ubuntu/Debian)

The NVIDIA driver alone does not make the GPU available inside Docker. Install and configure NVIDIA Container Toolkit. These commands configure the system Docker daemon and restart it; schedule the restart if other containers on this host must remain available.

Install the repository prerequisites, add NVIDIA's signed APT repository, and install the toolkit:

```sh
sudo apt-get update && sudo apt-get install -y --no-install-recommends ca-certificates curl gnupg2
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
  sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
```

For Fedora, RHEL, and other distributions, use the matching repository setup in NVIDIA's [Container Toolkit installation guide](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html); the repository configuration differs by distribution.

## 3. Register the Toolkit with Docker and Restart

The runtime configuration modifies Docker's daemon settings. Restarting Docker can interrupt other running containers, so schedule it appropriately.

```sh
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

## 4. Test GPU Passthrough Before Compose

Run the CUDA container smoke test before starting or changing the ROSIE Compose stack:

```sh
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

If your account cannot access the Docker socket, run the same test with `sudo`:

```sh
sudo docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

The output should list the Tesla P4 from inside the container. If it does, Docker GPU passthrough works; continue to step 5 to check model files, then step 6 to start ROSIE. If the CUDA image cannot be pulled, retry when registry access is available. If it starts but does not list the P4, troubleshoot the driver/toolkit before running Compose. The smoke-test image's CUDA 12.4 runtime is only for verifying passthrough; ROSIE's llama.cpp servers use the CUDA 12 `server-cuda` image.

## 5. Check ROSIE Model and GPU Settings

The repository defaults use `./models` and request up to 99 GPU layers. Check that the files named in `.env` exist and that the setting is present:

```sh
grep -E '^(LLAMA_MODELS_PATH|LLAMA_N_GPU_LAYERS|LLAMA_CTX_SIZE|LLAMA_CHAT_MODEL_FILE|LLAMA_EMBEDDING_MODEL_FILE)=' .env
ls -lh ./models/Llama-3.2-3B-Instruct-Q4_K_M.gguf ./models/nomic-embed-text-v1.5.Q4_K_M.gguf
```

`LLAMA_N_GPU_LAYERS=99` asks llama.cpp to offload all layers that the model has. It does not reserve 99 layers or guarantee that all layers fit in VRAM. If you use different filenames or a different model directory, update the corresponding `.env` values. The root README links the default model sources and licenses, and [configuration](../configuration.md#models-and-gpu) describes every model setting.

## 6. Start ROSIE with GPU Access

Compose already selects the CUDA 12 llama.cpp images and requests one NVIDIA GPU for each model service. Validate the resolved configuration, then start the stack:

```sh
sudo docker compose config --quiet
sudo docker compose up -d --build
sudo docker compose ps
```

Wait for both llama.cpp services to load their models. Inspect their startup logs:

```sh
sudo docker compose logs --tail=100 llama-chat llama-embeddings
```

Look for CUDA device detection and messages indicating layers were offloaded to the GPU. If a service exits or repeatedly restarts, continue to [Troubleshooting](#troubleshooting) before using chat or ingestion.

## 7. Verify GPU Use Through ROSIE

In one terminal, watch GPU memory and utilization:

```sh
watch -n 1 nvidia-smi
```

In another terminal, ask ROSIE a question. This exercises the chat model:

```sh
curl --fail-with-body --silent --show-error \
  --request POST http://localhost:8001/api/chat \
  --header 'Content-Type: application/json' \
  --data '{"question":"What operational documents are indexed?"}'
```

To exercise embeddings, ingest local documents. Put a supported document under `knowledge/` first; runbooks can go under `knowledge/runbooks/`:

```sh
curl --fail-with-body --silent --show-error \
  --request POST http://localhost:8001/api/ingest/local
```

The API should return file and chunk counts. While either request is running, `nvidia-smi` should show GPU memory in use and may show utilization. GPU utilization can be brief for short requests, so startup logs showing CUDA and layer offload are the stronger check that the model is configured for GPU execution.

## 8. Tune VRAM Use

If `llama-chat` reports CUDA allocation errors, fails to load, or exits during inference, check current GPU usage and reduce the offloaded layer count in `.env`:

```sh
nvidia-smi
sed -i 's/^LLAMA_N_GPU_LAYERS=.*/LLAMA_N_GPU_LAYERS=20/' .env
sudo docker compose up -d --force-recreate llama-chat llama-embeddings
sudo docker compose logs --tail=100 llama-chat llama-embeddings
```

Start with a lower value such as `20`, then increase it gradually if memory permits. The same setting applies to both services. Because both models share the P4, other GPU workloads also reduce the available headroom. The remaining layers run on the CPU when the selected value is lower than the model's total layer count.

The chat context size also consumes memory through the KV cache. The default is `LLAMA_CTX_SIZE=10240`. If memory is still insufficient after reducing GPU layers, lower the context size in `.env` and recreate the chat service:

```sh
sed -i 's/^LLAMA_CTX_SIZE=.*/LLAMA_CTX_SIZE=4096/' .env
sudo docker compose up -d --force-recreate llama-chat
sudo docker compose logs --tail=100 llama-chat
```

Use the lower context only if it meets your workload's needs. If answers fail with a context-length error afterwards, lower `CHAT_EVIDENCE_LIMIT` or `CHAT_MAX_OUTPUT_TOKENS` as well.

To restore the default full-offload request:

```sh
sed -i 's/^LLAMA_N_GPU_LAYERS=.*/LLAMA_N_GPU_LAYERS=99/' .env
sudo docker compose up -d --force-recreate llama-chat llama-embeddings
```

## Response Speed

On a card like the P4, most of the answer time is prompt processing and generation. Two app settings in `.env` trade answer quality for speed:

- `CHAT_EVIDENCE_LIMIT` (default `2`): passages sent with each question. Fewer passages mean a shorter prompt.
- `CHAT_MAX_OUTPUT_TOKENS` (default `512`): the longest answer. A lower limit caps generation time but can cut answers short.

Apply changes with `sudo docker compose up -d app`. Each answer shows its generation time, and the hardware footer on the chat page shows when thermal throttling is slowing the GPU.

## Troubleshooting

### Host sees the P4, but Docker reports no GPU

Check the toolkit configuration and rerun the CUDA container smoke test:

```sh
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
sudo docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

If Docker reports `could not select device driver` or an NVIDIA runtime error, check the installed toolkit and Docker runtime configuration:

```sh
nvidia-ctk --version
sudo docker info --format '{{json .Runtimes}}'
sudo journalctl -u docker --since '15 minutes ago' --no-pager
```

### A llama.cpp service has no CUDA device or fails to start

Check the service logs and resolved Compose image names. Both services should use `server-cuda`, not `server` or `server-cuda13`:

```sh
sudo docker compose config --quiet
grep -A20 '^  llama-chat:' docker-compose.yml
grep -A24 '^  llama-embeddings:' docker-compose.yml
sudo docker compose logs --tail=200 llama-chat llama-embeddings
```

### CUDA out-of-memory

Inspect processes and lower `LLAMA_N_GPU_LAYERS` as described above. If another workload is using the card, stop only workloads you are authorized to stop; do not terminate unknown processes. Chat may need CPU offload even when the GGUF file itself is smaller than total VRAM because context and runtime allocations also take memory.

### ROSIE returns a service-unavailable error

Check that all services are running, then inspect the llama.cpp and app logs. Embedding failures affect ingestion and search; chat failures affect investigations and runbook drafting.

```sh
sudo docker compose ps
sudo docker compose logs --tail=100 app llama-chat llama-embeddings
```

Do not publish ports 8080 or 8081 to untrusted networks. ROSIE reaches these services over the private Compose network; only the ROSIE web/API port is published by the current Compose file.
