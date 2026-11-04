# Runbooks

Runbooks are first-class operational artifacts in ROSIE. An investigation checks whether a relevant runbook exists, and ROSIE can draft new runbooks for review.

## Runbook Gap Detection

A runbook gap means a semantic search of indexed runbooks returned nothing scoring at least `RELEVANCE_THRESHOLD`. Every chat answer reports this, and `GET /api/runbooks/gap` checks it directly.

A gap does not prove that no runbook exists: one may be in a source ROSIE does not index. A match does not prove that the runbook is complete or current. Both need human review.

When a gap is found, ROSIE should explain why a runbook would help, the operational risk of not having one, and a proposed title.

## The Runbook Model

ROSIE stores a runbook as structured data, the `Runbook` model in `rosie/models.py`, and renders Markdown from it. The model is the source of truth; Markdown is an export format. The API reference at `/docs` shows the full schema.

| Section | Content |
| --- | --- |
| Title | A short name for the procedure. Also used as the export file name. |
| Purpose | What the runbook is for. |
| Scope | Systems and situations it covers, and what it does not. |
| Architecture context | Relevant components and how they connect. |
| Prerequisites | Access, tools, or approvals needed before starting. |
| Symptoms | Observable signs that the runbook applies. |
| Investigation steps | Read-only checks to confirm the cause. |
| Recovery steps | Actions that resolve the problem. |
| Verification steps | Checks that confirm recovery worked. |
| Rollback steps | How to undo the recovery if it makes things worse. |
| Monitoring notes | Alerts or metrics to watch afterwards. |

Dependencies, related documents, and revision history may be added to the model later.

## Authoring Standard

These apply to runbooks written by ROSIE and by people:

- Distinguish verified facts from assumptions, and mark untested steps as untested.
- Use numbered, procedural language inside each step, and state the expected result.
- Include rollback steps, or state explicitly that rollback is unknown.
- Prefer read-only investigation before any change.
- Generated runbooks are drafts until an operator reviews them.

## Drafting, Exporting, and Publishing

```text
Incident -> gap check -> structured draft -> human review -> export or publish -> Git commit by the operator
```

1. **Draft:** `POST /api/runbooks/draft` sends the incident description and up to six matching passages to the chat model and returns a `Runbook`. Nothing is saved.
2. **Export:** `POST /api/runbooks/export` renders a `Runbook` as Markdown and returns it as a file download. Each section becomes a heading; empty sections read "Not specified".
3. **Publish:** `POST /api/runbooks/publish` writes the Markdown to a relative path inside `RUNBOOK_PUBLISH_PATH` on the host (see [configuration](configuration.md#storage)). It refuses to overwrite an existing file or write outside that directory, and it never commits. Point `RUNBOOK_PUBLISH_PATH` at a checkout of your runbook repository, then review and commit the file yourself.

Published runbooks are not indexed automatically. Once they are on your runbook site, the next source sync picks them up; you can also upload them with `POST /api/ingest` using `kind=runbook`.

Markdown is the only export format in v0.1. HTML, PDF, DOCX, and ODT exports and documentation-platform publishing are on the [roadmap](roadmap.md).
