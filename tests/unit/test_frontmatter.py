import pytest

from app.storage import frontmatter

pytestmark = pytest.mark.unit


def test_roundtrip():
    meta = {"title": "Emily", "category": "people", "tags": ["a", "b"], "source_transcripts": ["t1"]}
    body = "- fact one\n- fact two"
    text = frontmatter.dumps(meta, body)
    parsed_meta, parsed_body = frontmatter.loads(text)
    assert parsed_meta == meta
    assert parsed_body == body


def test_loads_without_frontmatter():
    meta, body = frontmatter.loads("just a body\nwith lines")
    assert meta == {}
    assert body == "just a body\nwith lines"


def test_loads_tolerates_unterminated_frontmatter():
    meta, body = frontmatter.loads("---\ntitle: x\nno closing delimiter")
    assert meta == {}
    assert "no closing delimiter" in body
