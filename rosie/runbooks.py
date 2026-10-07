from rosie.models import Runbook


def to_markdown(runbook: Runbook) -> str:
    sections = [
        ("Purpose", [runbook.purpose]),
        ("Scope", [runbook.scope]),
        ("Architecture Context", [runbook.architecture_context]),
        ("Prerequisites", runbook.prerequisites),
        ("Symptoms", runbook.symptoms),
        ("Investigation Steps", runbook.investigation_steps),
        ("Recovery Steps", runbook.recovery_steps),
        ("Verification Steps", runbook.verification_steps),
        ("Rollback Steps", runbook.rollback_steps),
        ("Monitoring Notes", runbook.monitoring_notes),
    ]
    rendered = [f"# {runbook.title}"]
    for heading, entries in sections:
        rendered.extend(["", f"## {heading}"])
        if entries:
            rendered.extend(f"- {entry}" for entry in entries)
        else:
            rendered.append("- Not specified")
    return "\n".join(rendered) + "\n"
