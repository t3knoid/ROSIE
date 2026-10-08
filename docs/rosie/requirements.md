# ROSIE Development Requirements Document (Draft v0.1)

## 1. Project Overview

### Project Name

**ROSIE**

**Root-cause Observation, SRE Incident Examiner**

### Vision

ROSIE is a documentation-aware DevOps and Site Reliability Engineering assistant that behaves like an experienced senior infrastructure engineer.

ROSIE helps:

- Homelab operators
- Small businesses
- IT administrators
- Junior engineers
- Non-technical users

investigate, diagnose, document, and resolve infrastructure issues.

ROSIE prioritizes evidence-based troubleshooting and operational documentation over generic LLM responses.

### Core Principle

ROSIE is not an AI chatbot.

ROSIE is an operational intelligence platform that uses LLMs to:

- Understand infrastructure
- Analyze operational data
- Follow runbooks
- Generate documentation
- Guide troubleshooting

---

# 2. Primary Goals

## Goal 1

Provide senior-level troubleshooting guidance.

Example:

User:

> Plex isn't working.

ROSIE:

- Inspects available evidence.
- Searches documentation.
- Consults runbooks.
- Forms hypotheses.
- Explains findings.
- Suggests remediation.

---

## Goal 2

Leverage existing documentation.

ROSIE should:

- Read existing docs
- Understand architecture documentation
- Search incident records
- Search runbooks
- Reference previous solutions

---

## Goal 3

Reduce tribal knowledge.

ROSIE should continuously identify:

- undocumented procedures
- outdated runbooks
- configuration drift

---

## Goal 4

Generate operational documentation.

When operational knowledge is missing:

ROSIE should generate:

- Runbooks
- Incident reports
- Architecture documentation
- Lessons learned
- Recovery procedures

---

# 3. Target Users

## Primary User

Experienced:

- DevOps Engineers
- SREs
- Infrastructure Engineers
- Homelab Operators

---

## Secondary User

Junior engineers needing guidance.

ROSIE should explain:

- Why
- Not just what

---

## Tertiary User

Non-technical users.

ROSIE should:

- Avoid jargon
- Translate technical concepts
- Provide step-by-step instructions

---

# 4. System Architecture

```text
+----------------------+
| User Interface       |
+----------------------+
           |
           v
+----------------------+
| LangGraph Workflow   |
+----------------------+
           |
           v
+----------------------+
| LLM Layer            |
+----------------------+
           |
           v
+----------------------+
| Knowledge Layer      |
+----------------------+
      |
      +------------------+
      |                  |
      v                  v
 Documentation      Infrastructure
 Sources            Connectors
```

---

# 5. Recommended Technology Stack

## Language

Python 3.12+

---

## Agent Framework

LangGraph

Purpose:

- Investigation workflows
- State management
- Agent execution

---

## LLM Provider

Initially:

Ollama

Supported models:

- Qwen
- Llama
- DeepSeek

Future:

- OpenAI
- Azure OpenAI
- Anthropic
- Gemini

---

## Vector Database

Preferred:

Qdrant

Alternative:

Chroma

Purpose:

- Document search
- Runbook retrieval
- Knowledge retrieval

---

## API Framework

FastAPI

Purpose:

- REST API
- Integrations
- UI backend

---

## UI

Phase 1

Simple web interface

Future:

- React
- Next.js
- Chat UI

---

# 6. Core ROSIE Workflow

## Observe

Gather:

- Logs
- Metrics
- Errors
- Configuration data

Determine:

- Known facts
- Missing facts

---

## Correlate

Analyze:

- Dependencies
- Service relationships
- Recent changes

---

## Simulate

Create:

- Root cause hypotheses

Rank:

- High likelihood
- Medium likelihood
- Low likelihood

---

## Examine

Generate:

- Validation steps
- Diagnostic commands

---

## Remediate

Recommend:

- Recovery procedures
- Safe changes
- Rollback procedures

---

## Verify

Validate:

- Service restoration
- Health status
- Operational baseline

---

# 7. Documentation Layer

## Documentation Sources

Supported:

- Markdown
- HTML
- PDF
- DOCX
- ODT
- Wiki pages

Future:

- Confluence
- BookStack
- Wiki.js
- MediaWiki

---

## Documentation Repository

Authoritative source:

```text
https://homelab.refol.us
```

Runbooks:

```text
https://homelab.refol.us/runbooks.html
```

---

## Documentation Priority Order

1. Runtime evidence
2. Runbooks
3. Architecture documentation
4. User instructions
5. Industry best practice

---

# 8. Runbook Management System

## Objective

Runbooks are first-class citizens.

Every incident should answer:

```text
Did a runbook exist?

Was it sufficient?

Should it be updated?

Should a new one be created?
```

---

## Runbook Gap Detection

ROSIE should identify:

- Missing runbooks
- Incomplete runbooks
- Outdated runbooks
- Drift vs documentation

---

## Runbook Generation

ROSIE generates:

- Draft runbooks
- Updates to existing runbooks
- Incident recovery procedures

---

# 9. Internal Runbook Model

ROSIE should NEVER directly create Markdown.

Instead use a canonical model:

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

---

# 10. Document Export Framework

ROSIE generates structured documents.

Exporters render them into formats.

## Initial Formats

- Markdown
- HTML
- PDF

---

## Future Formats

- DOCX
- ODT
- MediaWiki
- Confluence

---

# 11. Documentation Publishing Framework

## Publisher Interface

```python
class Publisher:
    search()
    create()
    update()
    delete()
```

---

## Supported Providers

### Phase 1

Git repository

- GitHub
- GitLab
- Gitea
- Forgejo

---

### Phase 2

Documentation Platforms

- Confluence
- Wiki.js
- BookStack
- MediaWiki

---

# 12. Infrastructure Awareness

## Phase 1

Documentation only.

No infrastructure access required.

---

## Phase 2

Observability

Read-only integrations:

- Grafana
- Prometheus
- Loki

---

## Phase 3

Infrastructure

Read-only integrations:

- Docker
- Podman
- Kubernetes
- Proxmox
- VMware

---

## Phase 4

Networking

Read-only integrations:

- OPNsense
- pfSense
- UniFi
- MikroTik

---

# 13. Security Model

## Default Mode

Read-only.

ROSIE should not make changes.

---

## Optional Mode

Operator approved actions.

Example:

```text
ROSIE:
I recommend restarting Container X.

Execute?

[Approve]
[Reject]
```

---

## Future

Role-based access control.

---

# 14. Audit and Governance

All actions should be recorded.

Example:

```text
Timestamp
User
Question
Evidence Used
Runbooks Consulted
Actions Suggested
Documentation Updates Generated
```

---

# 15. ROSIE Documentation Library

```text
docs/rosie/
├── README.md
├── architecture.md
├── system-prompt.md
├── roadmap.md
├── changelog.md
├── lessons-learned.md
├── model-configurations.md
├── integrations.md
├── runbook-authoring-standard.md
└── developer-guide.md
```

---

# 16. MVP Definition (ROSIE v0.1)

The first working version should only do these things:

✅ Chat interface

✅ Ollama integration

✅ Qwen model support

✅ Documentation ingestion

✅ Qdrant vector storage

✅ Runbook search

✅ Documentation search

✅ Runbook gap identification

✅ Runbook generation

✅ Markdown export

✅ Git repository storage

Nothing else.

No Kubernetes.

No Proxmox.

No Grafana.

No infrastructure actions.

The MVP proves that ROSIE can act as a documentation-aware senior SRE before attempting infrastructure awareness.

---

# 17. Success Criteria

ROSIE is considered successful when it can:

1. Answer questions using local documentation.
2. Explain troubleshooting steps clearly.
3. Identify probable root causes.
4. Detect missing documentation.
5. Generate high-quality runbooks.
6. Help a junior engineer complete operational tasks.
7. Improve documentation after every incident.

**Short-term recommendation:** build the MVP as a FastAPI + LangGraph + Ollama + Qdrant application running in Docker Compose. If you complete that foundation first, every future capability (Proxmox, Kubernetes, Grafana, Confluence, etc.) becomes a plugin instead of a rewrite.
