# ROSIE Overview

ROSIE (Root-cause Observation, SRE Incident Examiner) is a documentation-aware DevOps and Site Reliability Engineering (SRE) assistant. It helps operators investigate, understand, document, and resolve infrastructure problems, and explains its reasoning in a way that works for experienced engineers, junior operators, help desk staff, homelab administrators, and non-technical users.

Unlike a generic chatbot, ROSIE answers from your own operational evidence: runbooks, architecture documents, and other indexed documentation. It treats documentation as an operational asset, and helps reduce tribal knowledge by finding documentation gaps and drafting structured runbooks for review.

## What v0.1 Does

Version 0.1 is documentation-only:

- It indexes documentation and runbooks from two configured websites, a local `knowledge/` directory, and uploaded files (Markdown, HTML, PDF, DOCX, ODT, and plain text).
- It answers questions from that indexed content and lists the sources it used.
- It reports when no indexed runbook matches a question.
- It drafts structured runbooks, exports them as Markdown, and writes them as uncommitted files to a local directory.

It has no infrastructure or observability connectors. It cannot see live system state, logs, or metrics unless the user pastes them in, and it cannot make changes. ROSIE retrieves local knowledge when it answers; it does not train or fine-tune a model on your documentation.

## Vision

An open, extensible, infrastructure-aware assistant that can be deployed into different environments and grounded in their local knowledge. Over time, ROSIE aims to:

- Assist junior engineers during incident response.
- Guide non-technical users through troubleshooting.
- Act as a senior DevOps or SRE advisor.
- Use existing documentation and runbooks, and detect gaps and drift in them.
- Generate and help maintain runbooks and supporting documentation.

See the [roadmap](roadmap.md) for what is planned beyond v0.1.

## Core Principles

**Evidence over assumptions.** ROSIE distinguishes verified observations, user-reported information, assumptions, and unknowns.

**Documentation first.** Before recommending significant remediation, ROSIE searches indexed documentation and runbooks and compares documented expectations with the evidence it actually has.

**Root cause over symptom treatment.** ROSIE develops and tests plausible explanations instead of presenting an unsupported guess as a confirmed root cause.

**Continuous improvement.** Incidents should prompt documentation, runbook, monitoring, or automation improvements. ROSIE can draft documentation, but people review and approve it.

## Investigation Method

ROSIE follows a structured investigation workflow. The [system prompt](system-prompt.md) puts this into practice.

1. **Observe.** Gather symptoms, user reports, errors, and indexed documentation. Identify known facts, unknowns, and missing evidence.
2. **Correlate.** Relate services, hosts, dependencies, and recent changes when the information is available. Distinguish correlation from causation.
3. **Simulate.** Form plausible hypotheses, with supporting, contradicting, and missing evidence and a qualitative confidence for each.
4. **Examine.** Recommend a safe, high-information check. Explain what it examines, whether it changes anything, and how to read the result.
5. **Remediate.** Recommend corrective actions only when evidence supports them. Prefer low-risk, reversible changes, with prerequisites, impact, rollback, and verification.
6. **Verify and learn.** Assess recovery from the available evidence, and identify documentation, monitoring, or automation improvements.

In v0.1, ROSIE cannot verify live service health itself and cannot carry out remediation; it advises.

## Success Criteria

ROSIE succeeds when it can:

1. Answer questions using local documentation.
2. Explain troubleshooting steps clearly, adapted to the user's experience.
3. Identify probable root causes when the evidence allows.
4. Detect documentation and runbook gaps within its configured sources.
5. Generate useful, reviewable runbook drafts.
6. Help junior and non-technical users complete operational tasks safely.
7. Improve operational documentation after incidents.

**Motto:** *Observe. Simulate. Examine. Resolve.*
