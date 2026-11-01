import markdown
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


def markdown_to_safe_html(source: str) -> str:
    rendered = markdown.markdown(source, extensions=["fenced_code", "sane_lists", "tables"])
    return nh3.clean(
        rendered,
        tags=_ALLOWED_TAGS,
        attributes={"a": {"href", "title"}},
        url_schemes={"http", "https", "mailto"},
        link_rel="noopener noreferrer",
    )