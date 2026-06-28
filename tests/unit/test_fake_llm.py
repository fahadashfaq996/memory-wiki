import pytest

from app.llm.client import FakeLLM, _parse_extraction, LLMError

pytestmark = pytest.mark.unit

TRANSCRIPT = """Sara: Did you finish the Q3 report?
John: I'll send it Friday. I'm joining the payments team.
Sara: Great, congrats."""


def test_fake_extract_creates_people_and_tasks():
    extraction = FakeLLM().extract(TRANSCRIPT)
    by_slug = {(i.category, i.slug) for i in extraction.items}
    assert ("people", "sara") in by_slug
    assert ("people", "john") in by_slug
    # John's "I'll send it Friday" is task-like.
    assert ("tasks", "open-items") in by_slug


def test_fake_extract_empty_transcript():
    assert FakeLLM().extract("   ") is not None
    assert FakeLLM().extract("no speaker lines here").items == []


def test_fake_merge_dedupes():
    merged = FakeLLM().merge(
        title="John",
        category="people",
        existing_body="- John likes coffee\n- John is an engineer",
        new_body="- John is an engineer\n- John joined payments",
    )
    lines = merged.splitlines()
    assert lines.count("- John is an engineer") == 1
    assert "- John joined payments" in lines


def test_parse_extraction_strips_code_fences():
    raw = '```json\n{"items": []}\n```'
    assert _parse_extraction(raw).items == []


def test_parse_extraction_invalid_json_raises():
    with pytest.raises(LLMError):
        _parse_extraction("not json at all")
