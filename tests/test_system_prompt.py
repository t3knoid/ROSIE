from langchain_core.messages import HumanMessage, SystemMessage

from rosie import workflow
from rosie.models import Runbook
from rosie.workflow import _evidence_context, build_investigation_graph, load_system_prompt


class FakeKnowledgeBase:
    def search(self, query: str, kind: str | None = None, limit: int = 5) -> list[dict[str, str | float]]:
        if kind == "runbook":
            return []
        return [{"text": "Service logs are stored in journald.", "source": "operations.md", "kind": "document", "score": 0.9}]


class FakeResponse:
    content = "Check the service logs."


class FakeLLM:
    messages = None

    def invoke(self, messages):
        self.messages = messages
        return FakeResponse()


def test_prompt_template_resolves_deployment_values() -> None:
    prompt = load_system_prompt()
    assert prompt.startswith("You are ROSIE.")
    assert "{{" not in prompt
    assert "no infrastructure integrations or actions in v0.1" in prompt
    assert len(prompt.split()) < 800
    assert "https://homelab.refol.us/" in prompt
    assert "https://homelab.refol.us/runbooks.html" in prompt
    assert "Observe. Simulate. Examine. Resolve." in prompt


def test_investigation_uses_full_prompt_as_system_message() -> None:
    llm = FakeLLM()
    graph = build_investigation_graph(FakeKnowledgeBase(), llm)

    result = graph.invoke({"question": "Where are service logs?"})

    assert isinstance(llm.messages[0], SystemMessage)
    assert "You are ROSIE." in llm.messages[0].content
    assert isinstance(llm.messages[1], HumanMessage)
    assert "Where are service logs?" in llm.messages[1].content
    assert "operations.md" in llm.messages[1].content
    assert result["answer"] == "Check the service logs."


def test_investigation_groups_legacy_duplicate_sources_and_preserves_distinct_passages() -> None:
    source = "https://homelab.refol.us/radarr.html"
    evidence = [
        {"source": source, "kind": "document", "text": "Check Radarr logs.", "score": 0.9},
        {"source": source, "kind": "runbook", "text": "Check Radarr logs.", "score": 0.9},
        {"source": source, "kind": "document", "text": "Verify the download client.", "score": 0.8},
        {"source": "other.md", "kind": "document", "text": "Check disk space.", "score": 0.7},
    ]

    class DuplicateKnowledgeBase:
        def search(self, query, kind=None, limit=5):
            return evidence[:1] if kind else evidence

    llm = FakeLLM()
    result = build_investigation_graph(DuplicateKnowledgeBase(), llm).invoke({"question": "Check Radarr"})
    context = llm.messages[1].content

    assert context.count(f"Source: {source}") == 1
    assert f"Source: {source} (document, runbook)" in context
    assert context.count("Check Radarr logs.") == 1
    assert context.count("Verify the download client.") == 1
    assert context.count("Source: other.md (document)") == 1
    assert result["evidence"] == evidence
    assert result["runbook_gap"] is False


def test_evidence_context_keeps_same_text_from_independent_sources() -> None:
    context = _evidence_context([
        {"source": "first.md", "kind": "document", "text": "Check logs."},
        {"source": "second.md", "kind": "runbook", "text": "Check logs."},
    ])
    assert context.count("Check logs.") == 2
    assert "Source: first.md (document)" in context
    assert "Source: second.md (runbook)" in context
    assert _evidence_context([]) == ""


def test_runbook_draft_groups_evidence_without_changing_canonical_output(monkeypatch) -> None:
    expected = Runbook(title="Radarr recovery", purpose="Recover Radarr.", scope="Draft only.")

    class DraftLLM(FakeLLM):
        def with_structured_output(self, model, method):
            assert model is Runbook
            assert method == "json_schema"
            return self

        def invoke(self, messages):
            self.messages = messages
            return expected

    llm = DraftLLM()
    monkeypatch.setattr(workflow, "ChatOpenAI", lambda **kwargs: llm)
    evidence = [
        {"source": "radarr.html", "kind": "document", "text": "Check logs."},
        {"source": "radarr.html", "kind": "runbook", "text": "Check logs."},
    ]

    assert workflow.draft_runbook("Radarr is down", evidence) is expected
    context = llm.messages[1].content
    assert context.count("Source: radarr.html") == 1
    assert context.count("Check logs.") == 1
    assert "(document, runbook)" in context


def test_prompt_says_evidence_is_excerpts() -> None:
    prompt = load_system_prompt()
    assert "never claim a document lacks something because an excerpt does not show it" in prompt
