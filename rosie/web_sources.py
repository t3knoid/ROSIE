from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx


@dataclass(frozen=True)
class WebPage:
    url: str
    title: str
    text: str


@dataclass(frozen=True)
class CrawlResult:
    pages: list[WebPage]
    errors: list[str]


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.links: list[str] = []
        self.title_parts: list[str] = []
        self.in_title = False
        self.hidden_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag in {"script", "style", "noscript", "svg"}:
            self.hidden_depth += 1
            return
        if self.hidden_depth:
            return
        if tag == "title":
            self.in_title = True
        if tag == "a" and attributes.get("href"):
            self.links.append(attributes["href"] or "")
        if tag in {"p", "br", "div", "li", "h1", "h2", "h3", "tr", "td", "th"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self.hidden_depth:
            self.hidden_depth -= 1
            return
        if self.hidden_depth:
            return
        if tag == "title":
            self.in_title = False
        if tag in {"p", "div", "li", "h1", "h2", "h3", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.hidden_depth:
            return
        self.parts.append(data)
        if self.in_title:
            self.title_parts.append(data)


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
    if path != "/" and not path.lower().endswith((".html", ".htm")):
        return None
    return urlunsplit(("https", parts.netloc.lower(), path, "", ""))


def crawl_html_source(
    source_url: str,
    *,
    max_pages: int = 100,
    timeout_seconds: float = 15,
    max_page_bytes: int = 2_000_000,
    transport: httpx.BaseTransport | None = None,
) -> CrawlResult:
    """Fetch one HTTPS seed and bounded same-origin HTML pages linked from it."""
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
                title = " ".join(" ".join(parser.title_parts).split())
                text = " ".join(" ".join(parser.parts).split())
                if text:
                    pages.append(WebPage(url=url, title=title, text=text))
                for href in parser.links:
                    candidate = _canonical_page_url(urljoin(url, href), origin)
                    if candidate and candidate not in visited and candidate not in queue and len(visited) + len(queue) < max_pages:
                        queue.append(candidate)
            except (httpx.HTTPError, UnicodeError, ValueError) as error:
                errors.append(f"{url}: {error}")

    return CrawlResult(pages=pages, errors=errors)