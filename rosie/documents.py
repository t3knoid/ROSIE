from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path

SUPPORTED_SUFFIXES = {".md", ".markdown", ".txt", ".html", ".htm", ".pdf", ".docx", ".odt"}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.hidden_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self.hidden_depth += 1
        elif tag in {"p", "br", "div", "li", "h1", "h2", "h3", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self.hidden_depth:
            self.hidden_depth -= 1
        elif tag in {"p", "div", "li", "h1", "h2", "h3", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.hidden_depth:
            self.parts.append(data)


def load_document(name: str, data: bytes) -> str:
    suffix = Path(name).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(f"Unsupported document type: {suffix or '(no extension)'}")
    if suffix in {".md", ".markdown", ".txt"}:
        return data.decode("utf-8-sig")
    if suffix in {".html", ".htm"}:
        parser = _TextExtractor()
        parser.feed(data.decode("utf-8", errors="replace"))
        return " ".join(" ".join(parser.parts).split())
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
        start = max(end - overlap, start + 1)
    return result
