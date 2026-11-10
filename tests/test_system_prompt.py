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
        def source_passages(self, source, kind):
            return []

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


def test_investigation_includes_and_names_the_matching_runbook() -> None:
    runbook_url = "https://homelab.refol.us/configure_an_inventory_host_web_service_for_a_reverse_proxy.html"
    document = {"source": "https://homelab.refol.us/nginx.html", "kind": "document", "text": "Nginx overview.", "score": 0.8}
    runbook = {"source": runbook_url, "kind": "runbook", "text": "Add the host to the proxy inventory.", "score": 0.7}

    class RunbookKnowledgeBase:
        def source_passages(self, source, kind):
            return []

        def search(self, query, kind=None, limit=5):
            return [runbook] if kind == "runbook" else [document]

    llm = FakeLLM()
    result = build_investigation_graph(RunbookKnowledgeBase(), llm).invoke({"question": "Reverse proxy setup"})
    context = llm.messages[1].content

    assert result["evidence"] == [document, runbook]
    assert result["runbook_gap"] is False
    assert f"Source: {runbook_url} (runbook)" in context
    assert "Add the host to the proxy inventory." in context
    assert f"closest indexed runbook is {runbook_url}" in context
    assert "If one helps answer the question, name it and give its steps; otherwise ignore it." in context
    assert "A runbook was found, so do not report a runbook gap." in context


def test_investigation_reports_runbook_gap_without_adding_evidence() -> None:
    document = {"source": "notes.md", "kind": "document", "text": "Notes.", "score": 0.8}

    class NoRunbookKnowledgeBase:
        def search(self, query, kind=None, limit=5):
            return [] if kind == "runbook" else [document]

    llm = FakeLLM()
    result = build_investigation_graph(NoRunbookKnowledgeBase(), llm).invoke({"question": "Anything"})

    assert result["evidence"] == [document]
    assert result["runbook_gap"] is True
    assert "no matching indexed runbook was found. You may report a runbook gap." in llm.messages[1].content


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


def test_prompt_says_not_to_guess_about_items_evidence_only_names() -> None:
    prompt = load_system_prompt()
    assert "answer with a plain list of the names exactly as written" in prompt
    assert "Do not add notes about what an item might contain or belong to." in prompt


def test_investigation_notes_an_answer_cut_off_at_the_output_limit(monkeypatch) -> None:
    class CutOffResponse:
        content = "Runbooks: Deploy Plex; Deploy"
        response_metadata = {"finish_reason": "length"}

    class CutOffLLM(FakeLLM):
        def invoke(self, messages):
            return CutOffResponse()

    monkeypatch.setattr(workflow.settings, "chat_max_output_tokens", 99)
    result = build_investigation_graph(FakeKnowledgeBase(), CutOffLLM()).invoke({"question": "List runbooks"})

    assert result["truncated"] is True
    assert result["answer"].startswith("Runbooks: Deploy Plex; Deploy\n\n*This answer was cut off at the output limit of 99 tokens.")
    assert "`CHAT_MAX_OUTPUT_TOKENS`" in result["answer"]


def test_investigation_does_not_flag_a_complete_answer() -> None:
    class CompleteResponse:
        content = "Check the service logs."
        response_metadata = {"finish_reason": "stop"}

    class CompleteLLM(FakeLLM):
        def invoke(self, messages):
            return CompleteResponse()

    result = build_investigation_graph(FakeKnowledgeBase(), CompleteLLM()).invoke({"question": "Logs?"})
    assert result["truncated"] is False
    assert result["answer"] == "Check the service logs."


def _runbook(source: str, score: float, text: str = "Steps.") -> dict[str, str | float]:
    return {"source": source, "kind": "runbook", "text": text, "score": score}


def test_nearly_tied_runbooks_are_both_given_to_the_model() -> None:
    passages = [_runbook("setup.html", 0.738), _runbook("setup.html", 0.719, "More setup."), _runbook("outage.html", 0.723)]
    assert workflow._closest_runbooks(passages) == [passages[0], passages[2]]


def test_a_clearly_better_runbook_stands_alone() -> None:
    passages = [_runbook("truenas.html", 0.872), _runbook("bootstrap.html", 0.82)]
    assert workflow._closest_runbooks(passages) == [passages[0]]
    assert workflow._closest_runbooks([]) == []


def test_investigation_names_both_tied_runbooks() -> None:
    passages = [_runbook("setup.html", 0.738, "Check the CNAME."), _runbook("outage.html", 0.723, "Check the backend first.")]

    class TiedKnowledgeBase:
        def source_passages(self, source, kind):
            return []

        def search(self, query, kind=None, limit=5):
            return passages if kind == "runbook" else []

    llm = FakeLLM()
    result = build_investigation_graph(TiedKnowledgeBase(), llm).invoke({"question": "502 Bad Gateway"})
    context = llm.messages[1].content

    assert result["evidence"] == passages
    assert result["runbook_gap"] is False
    assert "the closest indexed runbooks, nearly tied, are setup.html and outage.html. The first one's text" in context
    assert "No matching local documentation was found." not in context


def test_context_does_not_present_missing_connectors_as_an_observation() -> None:
    llm = FakeLLM()
    build_investigation_graph(FakeKnowledgeBase(), llm).invoke({"question": "Is the NAS up?"})
    context = llm.messages[1].content
    assert "No live infrastructure connectors" not in context
    assert "anything about their current state is unknown unless the user stated it" in context


def test_prompt_asks_for_runbook_steps_without_a_report_template() -> None:
    prompt = load_system_prompt()
    assert "give them in order, with commands exactly as written, and name the page" in prompt
    assert "without headings such as Verified Facts, Hypotheses, or Unknowns" in prompt
    assert "Never use either label for a page or runbook you cite." in prompt
    assert "never present a guess, or ROSIE's own configuration, as a fact about the user's systems" in prompt


def _stored(*texts: str, source: str = "certs.html") -> list[dict[str, str]]:
    return [{"source": source, "kind": "runbook", "text": text} for text in texts]


def test_runbook_text_is_given_in_page_order_up_to_the_limit() -> None:
    stored = _stored("Intro.", "1. Log in.", "2. Run generate_all_certs.yml.", "3. Verify in a browser.")
    matched = [{**stored[3], "score": 0.716}]
    result = workflow._runbook_text(stored, matched, limit=1000)
    assert [item["text"] for item in result] == [item["text"] for item in stored]
    assert all(item["score"] == 0.716 for item in result)


def test_long_runbook_keeps_its_start_and_the_matched_passage() -> None:
    stored = _stored("A" * 30, "B" * 30, "C" * 30, "D" * 30)
    matched = [{**stored[3], "score": 0.8}]
    result = workflow._runbook_text(stored, matched, limit=65)
    assert [item["text"][0] for item in result] == ["A", "B", "D"]


def test_investigation_gives_the_whole_runbook_in_page_order() -> None:
    source = "https://homelab.refol.us/request_web_certificates_runbook.html"
    stored = _stored("Intro.", "Run generate_all_certs.yml.", "Run stage_all_certs.yml.", "Verify in a browser.", source=source)
    verify = {**stored[3], "score": 0.716}
    document = {"source": "certbot.html", "kind": "document", "text": "Certbot overview.", "score": 0.7}

    class StoredKnowledgeBase:
        def search(self, query, kind=None, limit=5):
            return [verify] if kind == "runbook" else [verify, document]

        def source_passages(self, source_url, kind):
            return stored if source_url == source else []

    llm = FakeLLM()
    result = build_investigation_graph(StoredKnowledgeBase(), llm).invoke({"question": "Renew an expired certificate"})
    context = llm.messages[1].content

    assert [item["text"] for item in result["evidence"]] == ["Certbot overview."] + [item["text"] for item in stored]
    assert context.index("Run generate_all_certs.yml.") < context.index("Run stage_all_certs.yml.") < context.index("Verify in a browser.")
    assert f"the closest indexed runbook is {source}; its text, in page order, is in the evidence above." in context
