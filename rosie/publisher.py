from pathlib import Path
from typing import Protocol

from rosie.models import Runbook
from rosie.runbooks import to_markdown


class Publisher(Protocol):
    def search(self, query: str) -> list[dict[str, str]]: ...

    def create(self, path: str, runbook: Runbook) -> Path: ...

    def update(self, path: str, runbook: Runbook) -> Path: ...

    def delete(self, path: str) -> None: ...


class GitRepositoryPublisher:
    """Store generated Markdown in a checked-out Git repository without committing it."""

    def __init__(self, repository: str | Path) -> None:
        self.repository = Path(repository).resolve()
        self.repository.mkdir(parents=True, exist_ok=True)

    def _target(self, path: str) -> Path:
        relative = Path(path)
        if relative.is_absolute() or ".." in relative.parts or relative.suffix.lower() not in {".md", ".markdown"}:
            raise ValueError("Publisher paths must be relative Markdown paths inside the repository")
        target = (self.repository / relative).resolve()
        if not target.is_relative_to(self.repository):
            raise ValueError("Publisher path escapes the repository")
        return target

    def search(self, query: str) -> list[dict[str, str]]:
        needle = query.casefold()
        matches = []
        for path in self.repository.rglob("*.md"):
            text = path.read_text(encoding="utf-8")
            if needle in text.casefold():
                matches.append({"path": str(path.relative_to(self.repository)), "text": text})
        return matches

    def create(self, path: str, runbook: Runbook) -> Path:
        target = self._target(path)
        if target.exists():
            raise FileExistsError(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(to_markdown(runbook), encoding="utf-8")
        return target

    def update(self, path: str, runbook: Runbook) -> Path:
        target = self._target(path)
        if not target.is_file():
            raise FileNotFoundError(path)
        target.write_text(to_markdown(runbook), encoding="utf-8")
        return target

    def delete(self, path: str) -> None:
        self._target(path).unlink()
