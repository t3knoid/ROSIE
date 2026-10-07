import pytest

from rosie.documents import chunks, load_document


def test_loads_markdown_as_utf8_with_bom() -> None:
    assert load_document("notes.md", "\ufeffservice is healthy".encode()) == "service is healthy"


def test_html_loader_omits_scripts_and_normalizes_text() -> None:
    html = b"<h1>Storage</h1><script>ignore()</script><p>Disk is full.</p>"
    assert load_document("status.html", html) == "Storage Disk is full."


def test_chunks_overlap_and_cover_text() -> None:
    text = "one two three four five six seven eight nine ten"
    result = chunks(text, size=18, overlap=5)
    assert len(result) > 1
    assert "one" in result[0]
    assert "ten" in result[-1]
    assert result[0][-5:] in result[1]


def test_empty_and_unsupported_documents() -> None:
    assert chunks("  \n ") == []
    with pytest.raises(ValueError, match="Unsupported document type"):
        load_document("notes.exe", b"data")
