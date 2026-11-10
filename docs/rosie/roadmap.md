# Roadmap

## v0.1: Documentation MVP (current)

- Browser chat and REST API on FastAPI, with a LangGraph investigation workflow
- Local llama.cpp chat and embedding models (GGUF) and Qdrant storage
- Documentation and runbook ingestion from configured websites, local files, and uploads
- Evidence-aware answers with sources, and runbook gap checks
- Structured runbook drafts, Markdown export, and uncommitted drafts in a local Git checkout
- JSON Lines audit log

v0.1 includes no infrastructure actions and no live-system integrations.

## v0.2: Additional Export Formats

- HTML and PDF export
- DOCX and ODT export

## v0.3: Documentation Platforms

- Confluence, Wiki.js, BookStack, and MediaWiki integrations

## v0.4: Source-Control Workflows

- GitHub pull requests and GitLab merge requests
- Documentation review and approval workflows

## v1.0: Read-Only Infrastructure Awareness

- Read-only observability integrations (such as Grafana, Prometheus, and Loki)
- Read-only infrastructure and networking integrations
- Multi-platform documentation management

## Open Items

Smaller fixes and follow-ups not tied to a release are tracked in [GitHub Issues](https://github.com/t3knoid/ROSIE/issues).

## Not Yet Scheduled

- Authentication, roles, approvals, and multi-user audit identity
- Additional model providers
- Operator-approved actions, only after a separate threat model and approval design
