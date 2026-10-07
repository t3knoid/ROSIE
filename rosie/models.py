from pydantic import BaseModel, Field


class Evidence(BaseModel):
    source: str
    kind: str = "document"
    text: str
    score: float | None = None


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    answer: str
    evidence: list[Evidence]
    runbook_gap: bool


class Runbook(BaseModel):
    title: str
    purpose: str
    scope: str
    architecture_context: str = ""
    prerequisites: list[str] = Field(default_factory=list)
    symptoms: list[str] = Field(default_factory=list)
    investigation_steps: list[str] = Field(default_factory=list)
    recovery_steps: list[str] = Field(default_factory=list)
    verification_steps: list[str] = Field(default_factory=list)
    rollback_steps: list[str] = Field(default_factory=list)
    monitoring_notes: list[str] = Field(default_factory=list)


class RunbookDraftRequest(BaseModel):
    incident: str = Field(min_length=1, max_length=8000)


class PublishRequest(BaseModel):
    path: str = Field(min_length=1, max_length=240)
    runbook: Runbook
