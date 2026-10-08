# ROSIE

## Root-cause Observation, SRE Incident Examiner

### Overview

ROSIE is a documentation-aware DevOps and Site Reliability Engineering (SRE) assistant designed to help operators investigate, understand, document, and resolve infrastructure problems. It aims to behave like a seasoned infrastructure professional while making its reasoning accessible to experienced engineers, junior operators, help desk personnel, homelab administrators, and non-technical users.

Unlike a generic chatbot, ROSIE prioritizes operational evidence, runbooks, architecture documentation, and environmental context. It treats documentation as an operational asset and helps reduce tribal knowledge by finding documentation gaps and generating structured drafts for review.

In v0.1, ROSIE works from documents indexed locally, uploaded by an operator, or fetched by an explicit source-sync request. Operators can start a sync from the chat page with **Sync sources** or call `POST /api/ingest/sources`; the page remembers the last successful sync time in that browser. It has no live infrastructure or observability connectors and does not run a background web crawl.

---

# Vision

Create an open, extensible, infrastructure-aware assistant that can be deployed into different environments and grounded in their local knowledge sources.

ROSIE's long-term goals are to:

- Assist junior engineers during incident response.
- Guide non-technical users through troubleshooting.
- Act as a senior DevOps or SRE advisor.
- Leverage existing documentation and runbooks.
- Detect operational knowledge gaps and documentation drift.
- Generate and help maintain runbooks and supporting documentation.
- Improve documentation quality and reduce repeated operational effort.

ROSIE retrieves local knowledge at runtime; it does not train or fine-tune a model on private documentation.

---

# Core Principles

## Evidence Over Assumptions

ROSIE must distinguish verified observations, user-reported information, assumptions, and unknowns. In v0.1, runtime state, logs, and metrics are available only when supplied by the user; ROSIE does not inspect live systems.

## Documentation First

Before recommending significant remediation, ROSIE should search indexed documentation and runbooks, consult architecture references when available, and compare documented expectations with evidence it actually has. Incident-history search is a future capability unless incident records are ingested as local documents.

## Root Cause Over Symptom Treatment

ROSIE develops and validates plausible explanations instead of presenting an unsupported guess as a confirmed root cause.

## Continuous Improvement

Incidents should prompt consideration of documentation, runbook, monitoring, or automation improvements. ROSIE may draft documentation, but human review and approval remain necessary.

---

# ROSIE Methodology

ROSIE follows a structured investigation workflow:

## 1. Observe

Gather available symptoms, user reports, errors, and indexed documentation. Identify known facts, unknowns, and missing evidence. Live logs, metrics, configuration, and service health are not available in v0.1 unless the user provides them.

## 2. Correlate

Analyze relationships among services, hosts, infrastructure components, network dependencies, and recent changes when that information is present in user input or indexed documents. Distinguish correlation from causation.

## 3. Simulate

Develop plausible hypotheses and explain supporting evidence, contradictory or missing evidence, and qualitative confidence. Do not force a single root cause before evidence supports it.

## 4. Examine

Recommend a safe, high-information validation step. Explain what it examines, why it helps, whether it changes anything, and how to interpret the result.

## 5. Remediate

Recommend corrective actions only when supported by evidence. Prefer low-risk, reversible changes and include prerequisites, impact, rollback, and verification guidance. ROSIE v0.1 is advisory and cannot execute infrastructure changes.

## 6. Verify and Learn

Use available evidence to assess service restoration and stability. ROSIE cannot independently verify live service health in v0.1. At the end of an investigation, identify useful documentation, monitoring, or automation improvements.

---

# Documentation Sources

## v0.1 Ingestion Formats

- Markdown
- HTML
- PDF
- DOCX
- ODT
- Plain text

The API accepts uploaded files or indexes files placed under the local `knowledge/` directory. Wiki and documentation-platform connectors are future work.

## Authoritative Homelab References

- [Homelab Documentation](https://homelab.refol.us)
- [Homelab Runbooks](https://homelab.refol.us/runbooks.html)

These are the configured authoritative references for the initial homelab deployment. The chat page's **Sync sources** control, or `POST /api/ingest/sources`, fetches these pages and bounded same-origin HTML links on request; it does not crawl in the background. The displayed last-sync time is browser-local. Content can also be placed in the local knowledge directory or uploaded.

---

# Runbook Governance

Runbooks are first-class operational artifacts. An investigation should consider whether a relevant runbook exists, whether it appears applicable, and whether the available evidence suggests a documentation gap.

In v0.1, gap detection means that no matching runbook was returned by the indexed semantic search. It does not establish that a runbook is absent from sources ROSIE cannot access, or fully evaluate whether an existing runbook is complete or current. Those cases require human review.

When the local search identifies a gap, ROSIE should explain why a runbook may be useful, the operational risk of the gap, and a proposed title. It can generate a structured draft, not a publication-ready or validated procedure. Untested steps must be reviewed before use.

## Canonical v0.1 Runbook Model

ROSIE represents a runbook as structured data before rendering it into Markdown:

```python
class Runbook:
	title: str
	purpose: str
	scope: str
	architecture_context: str
	prerequisites: list
	symptoms: list
	investigation_steps: list
	recovery_steps: list
	verification_steps: list
	rollback_steps: list
	monitoring_notes: list
```

The model and authoring guidance are in [runbook-authoring-standard.md](runbook-authoring-standard.md). Additional governance metadata and sections such as dependencies, related documents, and revision history can be added as the model evolves.

---

# Documentation Export and Publishing

The v0.1 exporter renders the canonical runbook model as Markdown. HTML, PDF, DOCX, and ODT exports are not implemented yet.

The publishing adapter writes new Markdown drafts into a configured local, checked-out Git repository. It does not commit or push changes. GitHub, GitLab, Gitea, Forgejo, Confluence, Wiki.js, BookStack, and MediaWiki provider integrations are future work.

```text
Incident
	-> Runbook gap assessment
	-> Structured draft
	-> Human review
	-> Operator-managed Git commit or approved publication
```

---

# Technical Stack

- **Language:** Python 3.12+
- **Agent workflow:** LangGraph
- **LLM runtime:** Ollama; Qwen is the default chat model
- **Embeddings:** Ollama embedding model, configured separately from chat
- **API:** FastAPI
- **Vector database:** Qdrant
- **Deployment:** Docker Compose
- **Interface:** Simple browser-based chat and REST API

---

# Roadmap

## v0.1: Documentation MVP

- Chat interface and Ollama integration
- Local document ingestion and Qdrant storage
- Documentation and runbook retrieval
- Evidence-aware investigation and basic runbook-gap identification
- Structured runbook drafts and Markdown export
- Local Git-checkout draft storage

No infrastructure actions, Kubernetes, Proxmox, Grafana, or other live-system integrations are included.

## v0.2: Additional Export Formats

- HTML and PDF export
- DOCX and ODT export

## v0.3: Documentation Platforms

- Confluence, Wiki.js, BookStack, and MediaWiki integrations

## v0.4: Source-Control Workflows

- GitHub pull requests and GitLab merge requests
- Documentation review and approval workflows

## v1.0: Read-Only Infrastructure Awareness

- Read-only observability and infrastructure integrations
- Multi-platform documentation management
- Broader organizational knowledge lifecycle management

Any future write or remediation actions require a separate security and approval design.

---

# Success Criteria

ROSIE's product goals are to:

1. Answer questions using local documentation.
2. Explain troubleshooting steps clearly and adapt to the user's experience.
3. Identify probable root causes when evidence permits.
4. Detect documentation and runbook gaps within configured sources.
5. Generate useful, reviewable runbook drafts.
6. Help junior and non-technical users complete operational tasks safely.
7. Improve operational documentation after incidents.

These are target outcomes; they do not imply that live infrastructure observation or automatic documentation publication is available in v0.1.

---

**Motto:** *Observe. Simulate. Examine. Resolve.*

---

# Documentation Library

- [Requirements document](requirements.md) preserves the full Draft v0.1 specification.
- [Architecture](architecture.md) describes the v0.1 component boundaries.
- [System prompt](system-prompt.md) contains the complete runtime prompt.
- [Roadmap](roadmap.md) separates the documentation MVP from future integrations.
- [Changelog](changelog.md) tracks user-visible changes.
- [Lessons learned](lessons-learned.md) captures operational findings.
- [Model configurations](model-configurations.md) covers Ollama and Qwen.
- [Integrations](integrations.md) describes current service adapters.
- [Runbook authoring standard](runbook-authoring-standard.md) defines canonical runbook content.
- [Developer guide](developer-guide.md) describes local setup and checks.
