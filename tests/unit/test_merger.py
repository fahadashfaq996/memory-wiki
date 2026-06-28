import pytest

from app.llm.merger import merge_into_tree
from app.schemas.memory import MemoryExtraction, MemoryItem

pytestmark = pytest.mark.unit


def _extraction(slug, content, category="people", title="Subject"):
    return MemoryExtraction(items=[MemoryItem(category=category, slug=slug, title=title, content=content)])


def test_new_memory_is_written(memory_fs, fake_llm):
    written = merge_into_tree(memory_fs, fake_llm, _extraction("john", "- John is an engineer"), "t1")
    assert written == ["/people/john.md"]
    cat = memory_fs.cat("/people/john.md")
    assert "John is an engineer" in cat.content
    assert cat.metadata["source_transcripts"] == ["t1"]


def test_reprocessing_same_transcript_is_noop(memory_fs, fake_llm):
    merge_into_tree(memory_fs, fake_llm, _extraction("john", "- John is an engineer"), "t1")
    written = merge_into_tree(memory_fs, fake_llm, _extraction("john", "- John is an engineer"), "t1")
    assert written == []  # idempotent: same transcript contributes once
    cat = memory_fs.cat("/people/john.md")
    assert cat.metadata["source_transcripts"] == ["t1"]


def test_new_transcript_merges_and_tracks_sources(memory_fs, fake_llm):
    merge_into_tree(memory_fs, fake_llm, _extraction("john", "- John is an engineer"), "t1")
    merge_into_tree(memory_fs, fake_llm, _extraction("john", "- John joined payments"), "t2")
    cat = memory_fs.cat("/people/john.md")
    assert "John is an engineer" in cat.content
    assert "John joined payments" in cat.content
    assert cat.metadata["source_transcripts"] == ["t1", "t2"]
