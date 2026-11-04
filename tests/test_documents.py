import pytest

from rosie.documents import HtmlSectionParser, chunks, document_passages, load_document, markdown_sections, passages


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


SITE_PAGE = b"""<html><head><title>Home Lab Platform Overview</title></head><body>
<nav><a href="/">Home</a> <a href="/ansible.html">Ansible</a></nav>
<header><p>Site banner</p></header>
<main>
  <header><p>Updated weekly</p></header>
  <h1>&#x1F3E0; Home Lab Platform Overview</h1><p>A self-hosted platform.</p>
  <h2>Platform Foundation</h2><p>The lowest layer.</p>
  <h3>Networking</h3><ul><li>Pi-hole DNS</li></ul>
  <h3>Storage &amp; Data Protection</h3><ul><li>Ceph cluster</li><li>NFS from TrueNAS</li></ul>
  <h2>Identity</h2><p>Domain controller.</p>
  <script>ignored()</script>
</main>
<footer><p>Last published</p></footer>
</body></html>"""


def test_html_sections_follow_headings_and_skip_site_chrome() -> None:
    parser = HtmlSectionParser()
    parser.feed(SITE_PAGE.decode())
    assert parser.title == "Home Lab Platform Overview"
    assert parser.sections == [
        ((), "Updated weekly"),
        (("🏠 Home Lab Platform Overview",), "A self-hosted platform."),
        (("🏠 Home Lab Platform Overview", "Platform Foundation"), "The lowest layer."),
        (("🏠 Home Lab Platform Overview", "Platform Foundation", "Networking"), "Pi-hole DNS"),
        (("🏠 Home Lab Platform Overview", "Platform Foundation", "Storage & Data Protection"), "Ceph cluster NFS from TrueNAS"),
        (("🏠 Home Lab Platform Overview", "Identity"), "Domain controller."),
    ]
    for chrome in ("Ansible", "Site banner", "Last published", "ignored"):
        assert chrome not in parser.text


def test_passages_are_labeled_with_title_and_section() -> None:
    parser = HtmlSectionParser()
    parser.feed(SITE_PAGE.decode())
    result = passages(parser.title, parser.sections)
    assert result == [
        "Home Lab Platform Overview: Updated weekly",
        "Home Lab Platform Overview: A self-hosted platform.",
        "Home Lab Platform Overview › Platform Foundation: The lowest layer. Networking: Pi-hole DNS "
        "Storage & Data Protection: Ceph cluster NFS from TrueNAS",
        "Home Lab Platform Overview › Identity: Domain controller.",
    ]
    assert all(len(passage) <= 1200 for passage in passages("T", [((), "word " * 1000)]))
    assert all(passage.startswith("T: ") for passage in passages("T", [((), "word " * 1000)]))


def test_markdown_sections_ignore_headings_in_code_fences() -> None:
    title, sections = markdown_sections("# Disk full\nIntro.\n## Recovery\n```sh\n# not a heading\ndf -h\n```\n### Verify\nCheck space.\n")
    assert title == "Disk full"
    assert sections == [
        (("Disk full",), "Intro."),
        (("Disk full", "Recovery"), "```sh # not a heading df -h ```"),
        (("Disk full", "Recovery", "Verify"), "Check space."),
    ]
    assert document_passages("disk.md", b"# Disk full\n## Recovery\nFree space.") == ["Disk full › Recovery: Free space."]
    assert document_passages("notes.txt", b"plain text") == ["notes.txt: plain text"]


def test_short_subsections_merge_into_their_parent_but_topics_stay_separate() -> None:
    sections = [
        (("Reverse Proxy",), "Overview of the proxy."),
        (("Reverse Proxy", "HA Strategy"), "Active-passive."),
        (("Reverse Proxy", "HA Strategy", "Active Node"), "Receives traffic."),
        (("Reverse Proxy", "HA Strategy", "Passive Node"), "Stays warm."),
        (("Reverse Proxy", "Certificates"), "Certbot renews."),
        (("Reverse Proxy", "Certificates", "Renewal"), "x " * 400),
    ]
    result = passages("Reverse Proxy", sections)
    assert result[:3] == [
        "Reverse Proxy: Overview of the proxy.",
        "Reverse Proxy › HA Strategy: Active-passive. Active Node: Receives traffic. Passive Node: Stays warm.",
        "Reverse Proxy › Certificates: Certbot renews.",
    ]
    assert result[3].startswith("Reverse Proxy › Certificates › Renewal: x x")


def test_table_rows_keep_cells_apart() -> None:
    from rosie.documents import HtmlSectionParser

    parser = HtmlSectionParser()
    parser.feed("<table><tr><th>Runbook</th><th>Description</th></tr>"
                "<tr><td><a href='a.html'>Deploy <b>Plex</b></a></td><td></td><td>Install Plex.</td></tr></table><p>After.</p>")
    assert parser.text == "Runbook: Description; Deploy Plex: Install Plex.; After."


def test_runbook_index_passage_names_the_page_and_its_categories() -> None:
    from rosie.documents import runbook_index_passage

    sections = [((), "Intro."), (("📘 Runbooks",), "All runbooks."), (("📘 Runbooks", "🌐 DNS"), "Pi-hole."), (("📘 Runbooks", "🎬 Media"), "Plex.")]
    text = runbook_index_passage("Runbooks", "https://homelab.test/runbooks.html", sections, 12)
    assert text == (
        "Runbooks: This page, https://homelab.test/runbooks.html, is the runbook index. It lists all 12 runbooks, "
        "grouped by category: 🌐 DNS; 🎬 Media. Open it to see every runbook with a short description."
    )
