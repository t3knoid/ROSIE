from rosie.models import Runbook
from rosie.runbooks import to_markdown


def test_runbook_markdown_renders_all_canonical_sections() -> None:
    runbook = Runbook(
        title="Recover media service",
        purpose="Restore service availability.",
        scope="Single host.",
        prerequisites=["Confirm maintenance approval."],
        investigation_steps=["Check service health."],
    )
    markdown = to_markdown(runbook)
    assert markdown.startswith("# Recover media service\n")
    assert "## Investigation Steps\n- Check service health." in markdown
    assert "## Rollback Steps\n- Not specified" in markdown
