from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from rosie.documents import HtmlSectionParser, Section, _normalize


@dataclass(frozen=True)
class WebPage:
    url: str
    title: str
    text: str
    sections: tuple[Section, ...] = ()


@dataclass(frozen=True)
class IndexLink:
    """A page linked from a runbook index's main content."""

    url: str
    title: str
    """The link text; empty if the link has none."""
    heading: tuple[str, ...]
    """The heading path of the index section the link appears in."""


@dataclass(frozen=True)
class CrawlResult:
    pages: list[WebPage]
    errors: list[str]
    index_page: WebPage | None = None
    """For a runbook crawl, the index page itself. It is not a runbook, so it is kept apart."""
    index_links: tuple[IndexLink, ...] = ()
    """For a runbook crawl, each distinct page the index links to, in page order."""
    complete: bool = True
    """True when every reachable page was fetched: the crawl did not stop at the page limit, and
    every failure was a page that no longer exists (404 or 410). Only then is a page missing
    from `pages` known to be gone from the site."""


class _PageParser(HtmlSectionParser):
    """Section parser that also collects links, noting which are outside site navigation.

    Content links are also recorded with their text and the heading they appear under.
    """

    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.content_links: list[str] = []
        self.content_anchors: list[tuple[tuple[str, ...], str, str]] = []
        """(heading path, href, link text) for each content link."""
        self._anchor: tuple[str, list[str]] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        super().handle_starttag(tag, attrs)
        href = dict(attrs).get("href")
        if tag == "a" and href and not self.hidden_depth:
            self.links.append(href)
            if not self.chrome_depth:
                self.content_links.append(href)
                self._anchor = (href, [])

    def handle_endtag(self, tag: str) -> None:
        super().handle_endtag(tag)
        if tag == "a" and self._anchor:
            href, parts = self._anchor
            self.content_anchors.append((self.heading, href, _normalize(parts)))
            self._anchor = None

    def handle_data(self, data: str) -> None:
        super().handle_data(data)
        if self._anchor and not self.hidden_depth and not self.chrome_depth:
            self._anchor[1].append(data)


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
    index_page: WebPage | None = None
    index_links: dict[str, IndexLink] = {}
    headers = {"User-Agent": "ROSIE/0.1 documentation indexer"}
    complete = True

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
                page = WebPage(url=url, title=parser.title, text=text, sections=tuple(parser.sections)) if text else None
                if runbook_index and url == seed_url:
                    index_page = page
                elif page:
                    pages.append(page)
                links = parser.content_links if runbook_index and url == seed_url else parser.links
                if runbook_index and url != seed_url:
                    links = []
                if runbook_index and url == seed_url:
                    for heading, href, title in parser.content_anchors:
                        candidate = _canonical_page_url(urljoin(url, href), origin)
                        if candidate and candidate != seed_url and candidate not in index_links:
                            index_links[candidate] = IndexLink(url=candidate, title=title, heading=heading)
                for href in links:
                    candidate = _canonical_page_url(urljoin(url, href), origin)
                    if candidate and candidate not in visited and candidate not in queue:
                        if len(visited) + len(queue) < max_pages:
                            queue.append(candidate)
                        else:
                            complete = False
            except (httpx.HTTPError, UnicodeError, ValueError) as error:
                errors.append(f"{url}: {error}")
                gone = isinstance(error, httpx.HTTPStatusError) and error.response.status_code in (404, 410)
                if not gone or url == seed_url:
                    complete = False

    return CrawlResult(
        pages=pages,
        errors=errors,
        index_page=index_page,
        index_links=tuple(index_links.values()),
        complete=complete and not queue,
    )