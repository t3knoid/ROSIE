from langchain_core.messages import HumanMessage, SystemMessage

from rosie.workflow import build_investigation_graph, load_system_prompt


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
