import pytest

from rosie.models import Runbook
from rosie.publisher import GitRepositoryPublisher


def sample_runbook() -> Runbook:
    return Runbook(title="Disk recovery", purpose="Recover disk space.", scope="One host.")


def test_local_publisher_crud_and_search(tmp_path) -> None:
    publisher = GitRepositoryPublisher(tmp_path)
    path = publisher.create("runbooks/disk.md", sample_runbook())
    assert path.is_file()
    assert publisher.search("disk")
    publisher.update("runbooks/disk.md", sample_runbook().model_copy(update={"purpose": "Updated procedure."}))
    assert "Updated procedure" in path.read_text()
    publisher.delete("runbooks/disk.md")
    assert not path.exists()


@pytest.mark.parametrize("path", ["../outside.md", "/tmp/outside.md", "runbooks/notes.txt"])
def test_publisher_rejects_unsafe_paths(tmp_path, path: str) -> None:
    publisher = GitRepositoryPublisher(tmp_path)
    with pytest.raises(ValueError):
        publisher.create(path, sample_runbook())
