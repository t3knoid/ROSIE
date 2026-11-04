from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from rosie.documents import HtmlSectionParser, Section


@dataclass(frozen=True)
class WebPage:
    url: str
    title: str
    text: str
    sections: tuple[Section, ...] = ()


@dataclass(frozen=True)
class CrawlResult:
    pages: list[WebPage]
    errors: list[str]


class _PageParser(HtmlSectionParser):
    """Section parser that also collects links, noting which are outside site navigation."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.content_links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        super().handle_starttag(tag, attrs)
        href = dict(attrs).get("href")
        if tag == "a" and href and not self.hidden_depth:
            self.links.append(href)
            if not self.chrome_depth:
                self.content_links.append(href)


def _canonical_page_url(url: str, origin: tuple[str, str, int]) -> str | None:
    parts = urlsplit(url)
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError:
        return None
    if parts.scheme != "https" or not parts.hostname or (parts.scheme, parts.hostname.lower(), port) != origin:
        return None
    if parts.username or parts.password:
        return None
    path = parts.path or "/"
    if path.lower() in {"/index.html", "/index.htm"}:
        path = "/"  # The same page as the site root; index it once.
    if path != "/" and not path.lower().endswith((".html", ".htm")):
        return None
    return urlunsplit(("https", parts.netloc.lower(), path, "", ""))


def crawl_html_source(
    source_url: str,
    *,
    max_pages: int = 100,
    timeout_seconds: float = 15,
    max_page_bytes: int = 2_000_000,
    runbook_index: bool = False,
    transport: httpx.BaseTransport | None = None,
) -> CrawlResult:
    """Crawl HTTPS pages, or only content links directly listed in a runbook index."""
    seed = urlsplit(source_url)
    if seed.scheme != "https" or not seed.hostname or seed.username or seed.password:
        raise ValueError("Web documentation sources must be credential-free HTTPS URLs")
    if max_pages < 1 or timeout_seconds <= 0 or max_page_bytes < 1:
        raise ValueError("Crawl limits must be positive")
    origin = ("https", seed.hostname.lower(), seed.port or 443)
    seed_url = _canonical_page_url(source_url, origin)
    if seed_url is None:
        raise ValueError("Web documentation source must be an HTTPS page URL")

    queue = [seed_url]
    visited: set[str] = set()
    pages: list[WebPage] = []
    errors: list[str] = []
    headers = {"User-Agent": "ROSIE/0.1 documentation indexer"}

    with httpx.Client(
        timeout=timeout_seconds,
        follow_redirects=False,
        headers=headers,
        transport=transport,
    ) as client:
        while queue and len(visited) < max_pages:
            url = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)
            try:
                with client.stream("GET", url) as response:
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "").lower()
                    if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
                        raise ValueError("Source did not return HTML")
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > max_page_bytes:
                            raise ValueError("Page exceeded the configured size limit")
                    encoding = response.encoding or "utf-8"
                parser = _PageParser()
                parser.feed(bytes(body).decode(encoding, errors="replace"))
                text = parser.text
                if text and not (runbook_index and url == seed_url):
                    pages.append(WebPage(url=url, title=parser.title, text=text, sections=tuple(parser.sections)))
                links = parser.content_links if runbook_index and url == seed_url else parser.links
                if runbook_index and url != seed_url:
                    links = []
                for href in links:
                    candidate = _canonical_page_url(urljoin(url, href), origin)
                    if candidate and candidate not in visited and candidate not in queue and len(visited) + len(queue) < max_pages:
                        queue.append(candidate)
            except (httpx.HTTPError, UnicodeError, ValueError) as error:
                errors.append(f"{url}: {error}")

    return CrawlResult(pages=pages, errors=errors)