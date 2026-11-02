import re
from html import unescape
from xml.etree import ElementTree

import markdown
from markdown.extensions import Extension
from markdown.treeprocessors import Treeprocessor
import nh3


_ALLOWED_TAGS = {
    "a",
    "blockquote",
    "br",
    "code",
    "del",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "li",
    "ol",
    "p",
    "pre",
    "strong",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "ul",
}


class _InlineCodeLinks(Treeprocessor):
    def run(self, root: ElementTree.Element) -> None:
        def visit(element: ElementTree.Element) -> None:
            if element.tag in {"pre", "a"}:
                return
            if element.tag == "code" and not len(element):
                text = element.text or ""
                url = unescape(text)
                if re.fullmatch(r"https?://[^\s<>]+", url, flags=re.IGNORECASE):
                    element.text = None
                    ElementTree.SubElement(element, "a", {"href": url}).text = text
                return
            for child in element:
                visit(child)

        visit(root)


class _InlineCodeLinksExtension(Extension):
    def extendMarkdown(self, md: markdown.Markdown) -> None:
        md.treeprocessors.register(_InlineCodeLinks(md), "inline_code_links", 15)


def markdown_to_safe_html(source: str) -> str:
    rendered = markdown.markdown(
        source,
        extensions=["fenced_code", "sane_lists", "tables", "pymdownx.magiclink", _InlineCodeLinksExtension()],
    )
    return nh3.clean(
        rendered,
        tags=_ALLOWED_TAGS,
        attributes={"a": {"href", "title"}},
        url_schemes={"http", "https", "mailto"},
        link_rel="noopener noreferrer",
    )