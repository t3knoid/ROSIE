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