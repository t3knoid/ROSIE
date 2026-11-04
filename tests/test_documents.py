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


def test_chunks_start_and_end_on_word_boundaries() -> None:
    words = ["playbooks/truenas/deploy_truenas_vms.yml", "--check", "--diff", "variable", "truenas_vms", "list"]
    text = " ".join(words[i % len(words)] for i in range(600))
    result = chunks(text)
    assert len(result) > 3
    for passage in result:
        assert passage.split(" ")[0] in words
        assert passage.split(" ")[-1] in words
    for previous, current in zip(result, result[1:]):
        assert len(previous) <= 1200
        assert previous[-160:].split(" ", 1)[-1] in current


def test_chunks_still_split_text_without_spaces() -> None:
    result = chunks("x" * 3000)
    assert len(result) > 2
    assert "".join(passage[:-160] for passage in result[:-1]) + result[-1] == "x" * 3000
