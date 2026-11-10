# Changelog

## Unreleased

### Added

- Source sync runs automatically at startup and retries until it succeeds. Chat is unavailable until then, and the sync status is shared by all browsers.
- Optional host systemd timer for scheduled source syncs, configured with `SOURCE_SYNC_*` settings.
- Optional Tesla P4 thermal controller host service, with GPU model, VRAM, temperature, and fan status shown in a footer on the chat page and at `GET /api/health/gpu`.
- Optional Cloudflare Turnstile for public deployments. With `TURNSTILE_SITE_KEY` and `TURNSTILE_SECRET_KEY` set, the chat page shows the Turnstile widget, and `POST /api/chat` checks each question's token with Cloudflare before doing any work. `GET /api/config` gives the page its site key.
- The hardware panel has two parts. **System** shows fixed details, read once: CPU model, core and thread counts, total memory, and the GPU model, VRAM size and maximum clock. **Live** shows p4-thermal's readings, refreshed every 10 seconds: temperature, clock, power, utilization, VRAM used, and fans. The fixed details come from the new `GET /api/health/system`; CPU and memory are read from `/proc`, so the panel appears even without p4-thermal.
- `RUNBOOK_PUBLISH_PATH` chooses the host directory for published runbooks.
- All app settings in `.env`, including the organization and prompt context settings, now reach the app container.
- Swagger documentation at `/docs` with descriptions, examples, error codes, and typed responses for every endpoint.
- URLs in answers, including URLs in inline code, are clickable.
- Pressing Enter in the prompt sends the question; Shift+Enter adds a new line.
- A note under the prompt explains that each question is answered on its own, without earlier questions or answers.
- Source sync removes pages that are no longer on the site, such as a renamed or deleted page that now returns 404. It removes them only when the whole site was crawled without other errors and within `WEB_SOURCE_MAX_PAGES`, so a page that merely failed to load is kept. `POST /api/ingest/sources` reports `pages_removed`, and the sync status line shows the count.
- The sync status line shows how long the last sync took, and `POST /api/ingest/sources` and its status report `duration_seconds`.
- The default chat model is Llama 3.1 8B Instruct (Q4_K_M), the largest Q4 model that fits on the 8 GB Tesla P4 next to the embedding model. It follows instructions more closely than Llama 3.2 3B, such as listing runbook names without padding, but answers take longer.
- The runbook search result is given to the model as information, not an instruction, so answers that do not need it, such as a list of all runbooks, no longer end with "The best-matching indexed runbook is…".
- The model gets the closest runbook's text in page order, up to about 4,000 characters, not just its best-matching passage. Search often matched a runbook's notes or verification section rather than its steps, so answers said the steps were missing.
- When two runbooks match a question almost equally, both are given to the model. Previously, a setup runbook's troubleshooting table edged out the Web Service Outage runbook for "502 Bad Gateway" questions.
- The system prompt asks the model to give a runbook's steps and commands as written, drops the Verified Facts / Hypotheses template for how-to questions, and only allows "Documentation Gap" or "Runbook Gap" when the search found nothing. In a 10-question test, Llama 3.1 8B reported a gap in 6 answers while citing the right runbook.
- The question context no longer lists "No live infrastructure connectors" as a runtime observation; models were presenting it as a fact about the user's systems.
- The chat page has a favicon: a retro robot head in the page's colors, inlined as SVG.
- A [configuration reference](configuration.md), plus [source sync](operations/source-sync.md) and [troubleshooting](operations/troubleshooting.md) guides.

### Changed

- Replaced Ollama with separate llama.cpp chat and embedding servers using local GGUF models. The default chat model is Llama 3.2 3B Instruct.
- Shortened the system prompt and reduced evidence per question from four passages to two, for faster answers.
- Evidence lists each source once, with all its kinds; identical passages are sent to the model once.
- Pages found by both the documentation and runbook crawls are stored once, as runbooks; re-syncing removes conflicting older entries.
- The chat page uses its full width; hardware status moved from a sidebar to a compact footer.
- The app container mounts `docs/rosie` read-only and can write only to the publish directory.
- Reorganized the documentation; the original requirements draft is archived.

### Fixed

- Exporting a runbook whose title contains non-Latin-1 characters, quotes, or line breaks no longer fails.
- Large uploads no longer block other requests while they are processed.
- Unchanged passages are not re-embedded or duplicated when a source is re-indexed.
- Documents are split into passages at their headings, and each passage is labeled with its page and section. Previously, a fixed-size split could leave a heading in one passage and its content in the next, so content such as the home page's storage list was not found.
- Site navigation, headers, and footers are no longer indexed as page content.
- The site root's `/index.html` is no longer indexed separately from `/`; duplicates left by earlier versions are removed at the next sync.
- The system prompt tells the model that evidence passages are excerpts, so it no longer claims a page lacks information the excerpt does not show.
- When a runbook matches the question, its passage is included in the evidence and the model is told its URL, so answers name the runbook and it appears under **Evidence consulted**. Previously, the model was told only that a runbook matched, not which one.
- The runbook index page is indexed as a document, led by a passage saying it is the list of runbooks, with its runbook count and categories. Previously, the page was indexed only by the documentation crawl, and none of its passages said what the page was, so ROSIE answered that no list of runbooks existed.
- The runbook index's summary passage names every runbook, grouped by category. Previously, it named only the categories, and a question about all runbooks retrieved too few passages to see the runbook titles, so ROSIE listed only the one runbook that best matched.
- Answers cut off at `CHAT_MAX_OUTPUT_TOKENS` end with a note saying so, and `/api/chat` returns `truncated: true`. The default limit is raised from 512 to 1536 tokens, enough to list every runbook.
- The system prompt has a separate rule: when the evidence only names items, list the names as written, without notes about what each might contain. Previously, it padded each runbook in a list with speculation such as "likely part of the Runbook Ansible Template".
- Table cells are separated when pages are indexed, so a row reads "Deploy Plex: Step-by-step instructions…" instead of running the cells together.
- Passages no longer start in the middle of a word. Previously, the overlap between passages could cut names such as `deploy_truenas_vms.yml` to `enas_vms.yml`, and answers repeated the fragment.

## 0.1.0 - Initial MVP

- Added a documentation-only investigation workflow with FastAPI, LangGraph, Ollama, and Qdrant.
- Added supported document ingestion, semantic search, runbook gap assessment, structured runbook drafts, Markdown export, and local repository publishing.
- Added a browser chat, Docker Compose setup, and JSONL audit events.
