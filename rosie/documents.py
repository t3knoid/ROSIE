from html.parser import HTMLParser
import re
from io import BytesIO
from pathlib import Path

SUPPORTED_SUFFIXES = {".md", ".markdown", ".txt", ".html", ".htm", ".pdf", ".docx", ".odt"}


Section = tuple[tuple[str, ...], str]
"""A section of a document: its heading path (outermost first) and its text."""

_HEADING_LEVELS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4}
_HIDDEN_TAGS = {"script", "style", "noscript", "svg", "template"}
_CHROME_TAGS = {"nav", "header", "footer"}
_CONTENT_ROOTS = {"main", "article"}
_BLOCK_TAGS = {
    "p", "br", "div", "li", "ul", "ol", "dt", "dd", "tr", "td", "th", "table",
    "pre", "blockquote", "section", "h5", "h6",
}


def _normalize(parts: list[str]) -> str:
    return " ".join(" ".join(parts).split())


class HtmlSectionParser(HTMLParser):
    """Extract an HTML page's title and its text, split into sections at h1-h4 headings.

    Site chrome is left out: everything in <nav>, and <header> or <footer> outside
    <main> or <article>. Without that, every passage would start with the site menu.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hidden_depth = 0
        self.chrome_depth = 0
        self._chrome_stack: list[bool] = []
        self._content_depth = 0
        self._in_title = False
        self._title_parts: list[str] = []
        self._heading_level: int | None = None
        self._heading_parts: list[str] = []
        self._path: list[tuple[int, str]] = []
        self._sections: list[tuple[tuple[str, ...], list[str]]] = [((), [])]
        self._row_cells = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _HIDDEN_TAGS:
            self.hidden_depth += 1
            return
        if self.hidden_depth:
            return
        if tag in _CHROME_TAGS:
            is_chrome = tag == "nav" or not self._content_depth
            self._chrome_stack.append(is_chrome)
            self.chrome_depth += is_chrome
        if tag in _CONTENT_ROOTS:
            self._content_depth += 1
        if tag == "title":
            self._in_title = True
        if tag == "tr":
            self._row_cells = 0
        elif tag in {"td", "th"} and not self.chrome_depth and self._heading_level is None:
            # Separate cells so a table row reads "Name: description" rather than running together.
            if self._row_cells:
                self._append_separator(":")
            self._row_cells += 1
        if tag in _HEADING_LEVELS and not self.chrome_depth:
            self._heading_level = _HEADING_LEVELS[tag]
            self._heading_parts = []
        elif tag in _BLOCK_TAGS:
            self._sections[-1][1].append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in _HIDDEN_TAGS:
            if self.hidden_depth:
                self.hidden_depth -= 1
            return
        if self.hidden_depth:
            return
        if tag in _CHROME_TAGS and self._chrome_stack:
            self.chrome_depth -= self._chrome_stack.pop()
        if tag in _CONTENT_ROOTS and self._content_depth:
            self._content_depth -= 1
        if tag == "title":
            self._in_title = False
        if tag == "tr" and self._row_cells and not self.chrome_depth:
            self._append_separator(";")
        if tag in _HEADING_LEVELS and self._heading_level is not None:
            self._start_section()
        elif tag in _BLOCK_TAGS:
            self._sections[-1][1].append(" ")

    def handle_data(self, data: str) -> None:
        if self.hidden_depth:
            return
        if self._in_title:
            self._title_parts.append(data)
            return
        if self.chrome_depth:
            return
        if self._heading_level is not None:
            self._heading_parts.append(data)
        else:
            self._sections[-1][1].append(data)

    def _append_separator(self, mark: str) -> None:
        """Attach punctuation to the preceding text, without the block spacing before it."""
        parts = self._sections[-1][1]
        while parts and not parts[-1].strip():
            parts.pop()
        if parts:
            if not parts[-1].rstrip().endswith((":", ";")):
                parts[-1] = parts[-1].rstrip() + mark
            parts.append(" ")

    def _start_section(self) -> None:
        level, name = self._heading_level, _normalize(self._heading_parts)
        self._heading_level = None
        if not name:
            return
        self._path = [entry for entry in self._path if entry[0] < level] + [(level, name)]
        self._sections.append((tuple(entry[1] for entry in self._path), []))

    @property
    def title(self) -> str:
        return _normalize(self._title_parts)

    @property
    def sections(self) -> list[Section]:
        result = []
        for path, parts in self._sections:
            body = _normalize(parts)
            if body:
                result.append((path, body))
        return result

    @property
    def text(self) -> str:
        """All section text, each section preceded by its own heading."""
        return " ".join(" ".join(part for part in (path[-1] if path else "", body) if part) for path, body in self.sections)


_MARKDOWN_HEADING = re.compile(r"(#{1,4})\s+(.+?)\s*#*\s*$")


def markdown_sections(text: str) -> tuple[str, list[Section]]:
    """Split Markdown at #-#### headings (outside code fences). Returns the first h1 as the title."""
    title = ""
    path: list[tuple[int, str]] = []
    sections: list[tuple[tuple[str, ...], list[str]]] = [((), [])]
    in_fence = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("```", "~~~")):
            in_fence = not in_fence
        match = None if in_fence else _MARKDOWN_HEADING.fullmatch(stripped)
        if match:
            level, name = len(match.group(1)), match.group(2)
            if level == 1 and not title:
                title = name
            path = [entry for entry in path if entry[0] < level] + [(level, name)]
            sections.append((tuple(entry[1] for entry in path), []))
        else:
            sections[-1][1].append(line)
    return title, [(heading, body) for heading, parts in sections if (body := _normalize(parts))]


def _heading_key(text: str) -> str:
    return re.sub(r"\W+", "", text).casefold()


def section_label(title: str, heading: tuple[str, ...]) -> str:
    """Join the title and heading path, dropping a heading that repeats the title (ignoring emoji)."""
    parts: list[str] = []
    for part in (title, *heading):
        if part and (not parts or _heading_key(part) != _heading_key(parts[-1])):
            parts.append(part)
    return " › ".join(parts)


def merge_subsections(title: str, sections: list[Section], limit: int = 700) -> list[Section]:
    """Fold short subsections into their parent section while the result stays under `limit` characters.

    Only descendants merge, never siblings, so distinct topics stay in separate passages.
    Nothing merges into the page-level section (the title or h1), whose children are the
    page's main topics.
    A merged subsection keeps its heading inline, such as "Active Node: Receives all traffic".
    """
    merged: list[tuple[tuple[str, ...], str]] = []
    for heading, body in sections:
        if merged:
            parent, parent_body = merged[-1]
            is_page_level = section_label(title, parent) == section_label(title, ())
            if not is_page_level and len(heading) > len(parent) and heading[: len(parent)] == parent:
                addition = f"{' › '.join(heading[len(parent):])}: {body}"
                if len(parent_body) + len(addition) + 1 <= limit:
                    merged[-1] = (parent, f"{parent_body} {addition}")
                    continue
        merged.append((heading, body))
    return merged


def passages(title: str, sections: list[Section], size: int = 1200, overlap: int = 160) -> list[str]:
    """Chunk each section separately and prefix every passage with its title and section.

    Keeping sections apart stops a heading and its content from landing in different
    passages, and the prefix tells search and the model what each passage is about.
    """
    result: list[str] = []
    for heading, body in merge_subsections(title, sections):
        label = section_label(title, heading)
        prefix = f"{label}: " if label else ""
        for piece in chunks(body, size=max(size - len(prefix), size // 2), overlap=overlap):
            result.append(prefix + piece)
    return result


def runbook_index_passage(title: str, url: str, sections: list[Section], runbook_count: int) -> str:
    """Describe a runbook index page as a whole, so questions about the list itself find it.

    The index's own passages each hold one category of runbook links; none of them says that
    the page is the list of runbooks.
    """
    categories = list(dict.fromkeys(
        heading[0 if len(heading) == 1 else 1]
        for heading, _ in sections
        if heading and section_label(title, heading) != section_label(title, ())
    ))
    label = section_label(title, ()) or "Runbook index"
    text = f"{label}: This page, {url}, is the runbook index. It lists all {runbook_count} runbooks"
    if categories:
        text += f", grouped by category: {'; '.join(categories)}"
    return text + ". Open it to see every runbook with a short description."


def document_passages(name: str, data: bytes) -> list[str]:
    """Extract an uploaded or local file and split it into labeled passages."""
    suffix = Path(name).suffix.lower()
    if suffix in {".html", ".htm"}:
        parser = HtmlSectionParser()
        parser.feed(data.decode("utf-8", errors="replace"))
        return passages(parser.title or name, parser.sections)
    if suffix in {".md", ".markdown"}:
        title, sections = markdown_sections(data.decode("utf-8-sig"))
        return passages(title or name, sections)
    return passages(name, [((), load_document(name, data))])


def load_document(name: str, data: bytes) -> str:
    suffix = Path(name).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(f"Unsupported document type: {suffix or '(no extension)'}")
    if suffix in {".md", ".markdown", ".txt"}:
        return data.decode("utf-8-sig")
    if suffix in {".html", ".htm"}:
        parser = HtmlSectionParser()
        parser.feed(data.decode("utf-8", errors="replace"))
        return parser.text
    if suffix == ".pdf":
        import fitz

        with fitz.open(stream=data, filetype="pdf") as document:
            return "\n".join(page.get_text() for page in document)
    if suffix == ".docx":
        from docx import Document

        document = Document(BytesIO(data))
        return "\n".join(paragraph.text for paragraph in document.paragraphs)
    if suffix == ".odt":
        from odf import text, teletype
        from odf.opendocument import load

        document = load(BytesIO(data))
        return "\n".join(teletype.extractText(node) for node in document.getElementsByType(text.P))
    raise ValueError(f"Unsupported document type: {suffix}")


def chunks(text: str, size: int = 1200, overlap: int = 160) -> list[str]:
    clean = " ".join(text.split())
    if not clean:
        return []
    result: list[str] = []
    start = 0
    while start < len(clean):
        end = min(start + size, len(clean))
        if end < len(clean):
            boundary = clean.rfind(" ", start + size // 2, end)
            if boundary > start:
                end = boundary
        result.append(clean[start:end])
        if end == len(clean):
            break
        next_start = end - overlap
        # Begin the overlap at a word boundary. A passage that starts mid-word shows the
        # model a fragment such as "enas_vms.yml" for "deploy_truenas_vms.yml".
        if next_start > start and clean[next_start - 1] != " ":
            boundary = clean.rfind(" ", start + 1, next_start)
            if boundary != -1:
                next_start = boundary + 1
        start = max(next_start, start + 1)
    return result
