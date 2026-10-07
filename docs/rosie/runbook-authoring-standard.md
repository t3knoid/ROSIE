# Runbook Authoring Standard

Every runbook uses the canonical Pydantic `Runbook` model in `rosie/models.py`:

- Title, purpose, scope, and architecture context
- Prerequisites and symptoms
- Investigation, recovery, verification, and rollback steps
- Monitoring notes

Drafts must distinguish verified facts from assumptions. Prefer numbered procedural language inside each step, name expected results, and include a rollback or state explicitly when one is unknown. ROSIE stores the structured model in the API and uses `rosie/runbooks.py` to render Markdown. Generated content requires operator review before publication.
