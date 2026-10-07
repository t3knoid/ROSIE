from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "ROSIE"
    system_prompt_path: Path = Path(__file__).resolve().parents[1] / "docs/rosie/system-prompt.md"
    organization_name: str = "Not configured"
    environment_name: str = "Local ROSIE instance"
    environment_type: str = "Documentation-only MVP"
    documentation_sources: str = "Indexed local documents and uploads only; automatic web crawling is not configured."
    runbook_sources: str = "Indexed local runbook passages only."
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
    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "qwen2.5:7b"
    ollama_embedding_model: str = "nomic-embed-text"
    qdrant_url: str = "http://qdrant:6333"
    qdrant_collection: str = "rosie_documents"
    relevance_threshold: float = 0.35
    docs_path: str = "./knowledge"
    repository_path: str = "./docs/rosie/generated-runbooks"
    audit_log_path: str = "./data/audit.jsonl"


settings = Settings()
