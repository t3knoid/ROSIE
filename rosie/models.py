from typing import Literal

from pydantic import BaseModel, Field

Kind = Literal["document", "runbook"]


class Evidence(BaseModel):
    """A passage retrieved from the knowledge base."""

    source: str = Field(
        description="Where the passage came from: a page URL for synced sources, or a file name or path for uploads and local files.",
        examples=["https://homelab.refol.us/runbooks/disk-full.html"],
    )
    kind: str = Field("document", description="`document` or `runbook`.", examples=["runbook"])
    text: str = Field(description="The matching passage (up to about 1,200 characters).")
    score: float | None = Field(
        None,
        description="Cosine similarity between the query and the passage, from 0 to 1. Only passages at or above `RELEVANCE_THRESHOLD` are returned.",
        examples=[0.62],
    )


class ChatRequest(BaseModel):
    question: str = Field(
        min_length=1,
        max_length=4000,
        description="The incident, symptom, or question to investigate.",
        examples=["Nextcloud returns 502 Bad Gateway after a host reboot"],
    )


class ChatResponse(BaseModel):
    answer: str = Field(description="ROSIE's answer as Markdown.")
    answer_html: str = Field(description="`answer` rendered to sanitized HTML, safe to insert into a page.")
    evidence: list[Evidence] = Field(description="Passages given to the model as evidence, best match first.")
    runbook_gap: bool = Field(description="`true` when no indexed runbook matched the question.")
    truncated: bool = Field(
        False, description="`true` when the answer stopped at `CHAT_MAX_OUTPUT_TOKENS`; `answer` then ends with a note saying so."
    )
    duration_seconds: float = Field(description="Time taken to retrieve evidence and generate the answer.", examples=[14.2])


class Runbook(BaseModel):
    """A runbook in ROSIE's canonical structure. Each list item becomes one Markdown bullet on export."""

    title: str = Field(description="Runbook title; also used for the exported file name.", examples=["Recover from a full root disk"])
    purpose: str = Field(description="What the runbook is for.")
    scope: str = Field(description="Systems and situations it covers, and what it does not cover.")
    architecture_context: str = Field("", description="Relevant components and how they connect.")
    prerequisites: list[str] = Field(default_factory=list, description="Access, tools, or approvals needed before starting.")
    symptoms: list[str] = Field(default_factory=list, description="Observable signs that this runbook applies.")
    investigation_steps: list[str] = Field(default_factory=list, description="Read-only checks to confirm the cause.")
    recovery_steps: list[str] = Field(default_factory=list, description="Actions that resolve the problem.")
    verification_steps: list[str] = Field(default_factory=list, description="Checks that confirm recovery worked.")
    rollback_steps: list[str] = Field(default_factory=list, description="How to undo the recovery steps if they make things worse.")
    monitoring_notes: list[str] = Field(default_factory=list, description="Alerts or metrics to watch afterwards.")


class RunbookDraftRequest(BaseModel):
    incident: str = Field(
        min_length=1,
        max_length=8000,
        description="A description of the incident the runbook should cover.",
        examples=["The root filesystem on the Docker host fills up and containers stop writing logs"],
    )


class PublishRequest(BaseModel):
    path: str = Field(
        min_length=1,
        max_length=240,
        description="Relative path for the new file inside the publish repository. Must end in `.md` or `.markdown` and must not contain `..`.",
        examples=["storage/disk-full.md"],
    )
    runbook: Runbook


class HealthResponse(BaseModel):
    status: str = Field(description="Always `ok` when the API process is running.", examples=["ok"])
    service: str = Field(examples=["rosie"])


class IngestResult(BaseModel):
    source: str = Field(description="The file name the content is stored under. Uploading the same name again replaces it.", examples=["disk-full.md"])
    kind: Kind
    chunks: int = Field(description="Number of passages indexed.", examples=[4])


class LocalIngestResult(BaseModel):
    files: int = Field(description="Number of supported files found and indexed.", examples=[12])
    chunks: int = Field(description="Total passages indexed across all files.", examples=[87])


class PagesByKind(BaseModel):
    document: int = Field(description="Pages indexed as documentation.")
    runbook: int = Field(description="Pages indexed as runbooks.")


class SourceSyncResult(BaseModel):
    pages: int = Field(description="Unique pages indexed in this sync (not the total stored).", examples=[42])
    chunks: int = Field(description="Passages indexed in this sync.", examples=[310])
    pages_by_kind: PagesByKind
    pages_removed: int = Field(
        default=0,
        description="Pages removed from the index because they are no longer on their site. Pages are removed only when the site was crawled completely.",
        examples=[1],
    )
    errors: list[str] = Field(
        description="Pages that could not be fetched or parsed, as `URL: reason`. A non-empty list means a partial failure.",
        examples=[[]],
    )
    duration_seconds: float = Field(description="Time the sync took, from the first fetch to the last passage indexed.", examples=[84.3])


class SourceSyncStatus(BaseModel):
    ready: bool = Field(description="`true` once one sync has finished with no errors. `/api/chat` returns 503 until then.")
    syncing: bool = Field(description="`true` while a sync is running.")
    last_success: str | None = Field(description="ISO 8601 UTC time of the last sync with no errors, or `null`.", examples=["2026-11-04T09:15:02.481Z"])
    error: str | None = Field(description="Error from the most recent sync, or `null` if it succeeded.")
    result: SourceSyncResult | None = Field(description="Counts from the most recent sync that indexed at least one page, or `null`.")


class RunbookGapResult(BaseModel):
    gap: bool = Field(description="`true` when no indexed runbook matched.")
    assessment: str = Field(description="A one-sentence summary of the result.")
    evidence: list[Evidence] = Field(description="Up to 3 matching runbook passages.")


class PublishResult(BaseModel):
    path: str = Field(description="Absolute path of the file written inside the container.")
    status: str = Field(examples=["written; review and commit with Git"])


class ErrorResponse(BaseModel):
    detail: str = Field(description="What went wrong.")


class SourceSyncFailureDetail(BaseModel):
    message: str = Field(examples=["No configured documentation pages could be fetched."])
    errors: list[str] = Field(description="Per-page errors as `URL: reason`.")


class SourceSyncFailure(BaseModel):
    detail: SourceSyncFailureDetail
