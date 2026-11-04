from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "ROSIE"
    system_prompt_path: Path = Path(__file__).resolve().parents[1] / "docs/rosie/system-prompt.md"
    organization_name: str = "Not configured"
    environment_name: str = "Local ROSIE instance"
    environment_type: str = "Documentation-only MVP"
    documentation_sources: str = "https://homelab.refol.us/ plus local documents and uploads; synced at startup, on the optional host timer, and on request."
    runbook_sources: str = "https://homelab.refol.us/runbooks.html plus local runbooks and uploads; synced with the documentation sources."
    incident_sources: str = "Not configured"
    architecture_sources: str = "Indexed local architecture documents, when available."
    infrastructure_connectors: str = "None; infrastructure access is out of scope for v0.1."
    observability_connectors: str = "None configured."
    documentation_publishers: str = "Local checked-out Git repository; writes uncommitted Markdown drafts only."
    default_document_format: str = "Markdown"
    supported_document_formats: str = "Markdown export; Markdown, HTML, PDF, DOCX, ODT, and plain-text ingestion."
    default_user_level: str = "Accessible technical language; adapt to the user's demonstrated experience."
    action_policy: str = "Advisory only; no infrastructure integrations or actions in v0.1."
    approval_policy: str = "Infrastructure actions are unavailable; publishing requires an explicit API request and creates a draft only."
    restricted_systems: str = "All infrastructure systems; none are connected in v0.1."
    sensitive_data_policy: str = "Do not request or store secrets; ask users to redact sensitive operational data."
    escalation_configuration: str = "Not configured; advise the user to contact their responsible operator or service owner."
    documentation_source_url: str = "https://homelab.refol.us/"
    runbook_source_url: str = "https://homelab.refol.us/runbooks.html"
    web_source_max_pages: int = 100
    web_source_timeout_seconds: float = 15
    web_source_max_page_bytes: int = 2_000_000
    source_sync_enabled: bool = True
    source_sync_interval_seconds: int = Field(default=3600, gt=0)
    source_sync_api_url: str = "http://127.0.0.1:8001/api/ingest/sources"
    source_sync_timeout_seconds: float = Field(default=3600, gt=0)
    chat_evidence_limit: int = 2
    chat_max_output_tokens: int = 512
    llama_chat_base_url: str = "http://localhost:8080/v1"
    llama_embedding_base_url: str = "http://localhost:8081/v1"
    llama_chat_model: str = "local-chat"
    llama_embedding_model: str = "local-embedding"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "rosie_documents"
    relevance_threshold: float = 0.35
    docs_path: str = "./knowledge"
    repository_path: str = "./docs/rosie/generated-runbooks"
    audit_log_path: str = "./data/audit.jsonl"


settings = Settings()
