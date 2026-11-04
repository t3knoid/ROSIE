# Troubleshooting

Start with the service state and recent logs:

```sh
sudo docker compose ps
sudo docker compose logs --tail=100 app llama-chat llama-embeddings qdrant
curl -s http://localhost:8001/api/ingest/sources/status
```

## The prompt stays disabled, or chat returns "Sources must finish syncing"

Chat is unavailable after every app start until a source sync finishes with no errors. The status line under the prompt shows the sync state and any error.

- **"Waiting for initial source sync" or "Syncing":** the first sync is still running. On a first install, this includes embedding every page and can take several minutes.
- **"Source sync reported partial failures":** at least one page failed, often a broken or redirecting link on the source site. Fix the link or the setting named in the error; the app retries every 30 seconds. See [source sync](source-sync.md#readiness).
- **"No configured documentation pages could be fetched":** check `DOCUMENTATION_SOURCE_URL` and `RUNBOOK_SOURCE_URL`, and that the container can reach them.

## Chat or runbook drafts return "could not reach its llama.cpp or Qdrant service"

A model server or Qdrant is down or still loading. Check that all four services are running and that both llama.cpp logs show the model loaded. Embedding failures also break ingestion and search (which return HTTP 500); chat-model failures break answers and runbook drafts. For GPU problems, see [GPU troubleshooting](gpu-acceleration.md#troubleshooting).

## A llama.cpp server will not start or runs out of memory

See [Tune VRAM Use](gpu-acceleration.md#8-tune-vram-use) and [GPU troubleshooting](gpu-acceleration.md#troubleshooting).

## Answers say no documentation was found, or cite the wrong pages

- Check what was indexed: `curl -s "http://localhost:8001/api/search?q=<your topic>&limit=10"`.
- If relevant pages are missing, check the last sync's counts and errors, and whether the pages are reachable by the crawler's rules ([what a sync does](source-sync.md#what-a-sync-does)).
- If matches exist but score just under the cut-off, lower `RELEVANCE_THRESHOLD` a little. If weak matches are cited, raise it.
- If you changed the embedding model, re-index into a new collection ([changing the embedding model](../configuration.md#changing-the-embedding-model)).

## Answers are slow or cut off

See [response speed](gpu-acceleration.md#response-speed). The hardware footer on the chat page shows if the GPU is throttling.

## Uploads fail

| Status | Cause |
| --- | --- |
| 413 | File larger than 10 MB. |
| 415 | Unsupported file type. Use Markdown, HTML, PDF, DOCX, ODT, or plain text. |
| 422 | No text could be extracted; scanned PDFs without a text layer have none. |
| 400 | The file could not be parsed. |

## Publishing fails

`POST /api/runbooks/publish` returns 400 if the path is absolute, contains `..`, does not end in `.md` or `.markdown`, or the file already exists. Published files are owned by root on the host; use `sudo` or `chown` to edit or commit them.

## The hardware footer is missing or out of date

The footer appears only when the [thermal controller](p4-thermal-controller.md) is running and `/run/p4-thermal` is mounted into the app. "Out of date" means the controller has not written the status file for 30 seconds; check `systemctl status p4-thermal.service`. If the controller started after the app, recreate the app with `sudo docker compose up -d --force-recreate app`.
