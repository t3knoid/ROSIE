import pytest

from rosie.rendering import markdown_to_safe_html


@pytest.mark.parametrize("delimiter", ["`", "``"])
def test_url_only_inline_code_is_clickable(delimiter) -> None:
    urls = [
        "https://homelab.refol.us/add_truenas_local_users.html",
        "https://homelab.refol.us/truenas_role_contributor_guide.html",
    ]
    source = (
        f"1. {delimiter}{urls[0]}{delimiter} (runbook)\n"
        f"2. {delimiter}{urls[1]}{delimiter} (document)"
    )

    rendered = markdown_to_safe_html(source)

    assert "<ol>" in rendered
    assert rendered.count("<a ") == 2
    for url in urls:
        assert f'<code><a href="{url}"' in rendered
        assert f">{url}</a></code>" in rendered
    assert "(runbook)" in rendered
    assert "(document)" in rendered


@pytest.mark.parametrize("source", [
    "`curl https://example.test/page.html`",
    "```\nhttps://example.test/page.html\n```",
    "    https://example.test/page.html",
    "[`https://example.test/page.html`](https://example.test/target.html)",
])
def test_commands_code_blocks_and_existing_links_are_preserved(source) -> None:
    rendered = markdown_to_safe_html(source)
    if source.startswith("["):
        assert rendered.count("<a ") == 1
        assert 'href="https://example.test/target.html"' in rendered
    else:
        assert "<a " not in rendered
    assert "<code>" in rendered


@pytest.mark.parametrize("source", [
    "`javascript:alert(1)`",
    "`data:text/html,test`",
    "`file:///etc/passwd`",
    "`https://example.test/<script>alert(1)</script>`",
])
def test_inline_code_linkification_does_not_allow_unsafe_links(source) -> None:
    rendered = markdown_to_safe_html(source)
    assert "<a " not in rendered
    assert "<script>" not in rendered


def test_inline_url_queries_are_escaped_without_losing_parameters() -> None:
    rendered = markdown_to_safe_html('`https://example.test/page.html?a=1&b="two"#section`')
    assert 'href="https://example.test/page.html?a=1&amp;b=&quot;two&quot;#section"' in rendered
    assert rendered.count("<a ") == 1
