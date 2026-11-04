import httpx

from rosie.web_sources import crawl_html_source


def test_crawl_follows_only_same_origin_html_links_within_limit() -> None:
    bodies = {
        "https://homelab.test/runbooks.html": b"""
            <html><head><title>Runbooks</title></head><body>
            <h1>Runbooks</h1><a href='/plex_runbook.html'>Plex</a>
            <a href='https://other.test/private.html'>External</a>
            <a href='/assets/site.css'>Styles</a><script><a href='/bad.html'>Bad</a></script>
            </body></html>
        """,
        "https://homelab.test/plex_runbook.html": b"<html><body><h1>Plex recovery</h1><p>Check service logs.</p></body></html>",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        body = bodies.get(str(request.url))
        if body is None:
            return httpx.Response(404)
        return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, content=body)

    result = crawl_html_source(
        "https://homelab.test/runbooks.html",
        max_pages=5,
        transport=httpx.MockTransport(handler),
    )

    assert [page.url for page in result.pages] == [
        "https://homelab.test/runbooks.html",
        "https://homelab.test/plex_runbook.html",
    ]
    assert result.pages[0].title == "Runbooks"
    assert "Check service logs." in result.pages[1].text
    assert not result.errors


def test_crawl_enforces_page_limit() -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        body = b"<a href='/second.html'>Second</a>"
        return httpx.Response(200, headers={"content-type": "text/html"}, content=body)

    result = crawl_html_source(
        "https://homelab.test/",
        max_pages=1,
        transport=httpx.MockTransport(handler),
    )

    assert len(result.pages) == 1
    assert requested == ["https://homelab.test/"]


def test_runbook_index_excludes_navigation_index_and_recursive_links() -> None:
    requested: list[str] = []
    bodies = {
        "/runbooks.html": """
            <header><a href="/overview.html">Overview</a></header>
            <nav><a href="/">Home</a><a href="/runbooks.html">Runbooks</a></nav>
            <main><a href="/recovery.html">Recovery</a>
            <a href="/recovery.html#checks">Checks</a>
            <a href="https://other.test/runbook.html">External</a></main>
            <footer><a href="/about.html">About</a></footer>
        """,
        "/recovery.html": '<h1>Recovery</h1><a href="/architecture.html">Reference</a>',
    }

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        return httpx.Response(200, headers={"content-type": "text/html"}, text=bodies[request.url.path])

    result = crawl_html_source(
        "https://homelab.test/runbooks.html",
        runbook_index=True,
        transport=httpx.MockTransport(handler),
    )

    assert requested == ["/runbooks.html", "/recovery.html"]
    assert [page.url for page in result.pages] == ["https://homelab.test/recovery.html"]
    assert not result.errors


def test_empty_runbook_index_does_not_count_as_a_runbook() -> None:
    result = crawl_html_source(
        "https://homelab.test/runbooks.html",
        runbook_index=True,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, headers={"content-type": "text/html"}, text="<h1>Runbooks</h1>")
        ),
    )
    assert result.pages == []
    assert result.errors == []

def test_root_index_page_is_the_same_page_as_root_and_chrome_is_not_indexed() -> None:
    requested: list[str] = []
    bodies = {
        "/": '<nav><a href="/index.html">Home</a></nav><main><h1>Home</h1><p>Overview.</p><a href="/index.html">Again</a></main>',
    }

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        return httpx.Response(200, headers={"content-type": "text/html"}, text=bodies[request.url.path])

    result = crawl_html_source("https://homelab.test/index.html", transport=httpx.MockTransport(handler))

    assert requested == ["/"]
    assert [page.url for page in result.pages] == ["https://homelab.test/"]
    assert result.pages[0].sections == ((("Home",), "Overview. Again"),)
    assert "Home Overview" in result.pages[0].text
