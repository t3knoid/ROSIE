# Integrations

## Implemented in v0.1

- **Authoritative documentation:** `https://homelab.refol.us`; runbook reference: `https://homelab.refol.us/runbooks.html`. `POST /api/ingest/sources` explicitly fetches the configured HTTPS seeds and bounded same-origin HTML links. Local files and uploads are also supported; no background crawl runs.
- **Ollama:** chat and embeddings over its HTTP API.
- **Qdrant:** vector collection for indexed passages with source and document-kind metadata.
- **Local Git checkout:** a publisher protocol and filesystem-backed implementation for Markdown drafts. ROSIE does not commit or push.

## Not Implemented

Grafana, Prometheus, Loki, Docker, Kubernetes, Proxmox, VMware, network devices, and wiki platforms are future integrations. No infrastructure actions are available in this release.
