import pytest

from app.storage import frontmatter
from app.storage.memory_fs import MemoryFS

pytestmark = pytest.mark.unit


def _seed(fs: MemoryFS):
    fs.write_raw("people/emily.md", frontmatter.dumps({"title": "Emily"}, "- Emily is an engineer\n- Emily likes coffee"))
    fs.write_raw("people/john.md", frontmatter.dumps({"title": "John"}, "- John joined the payments team"))
    fs.write_raw("tasks/open-items.md", frontmatter.dumps({"title": "Open Items"}, "- Send the Q3 report by Friday"))


def test_ls_root_lists_directories(memory_fs):
    _seed(memory_fs)
    res = memory_fs.ls("/")
    dirs = {e.name for e in res.entries if e.type == "dir"}
    assert {"people", "tasks"} <= dirs


def test_ls_directory_lists_files(memory_fs):
    _seed(memory_fs)
    res = memory_fs.ls("/people")
    files = {e.name: e for e in res.entries}
    assert "emily.md" in files
    assert files["emily.md"].type == "file"
    assert files["emily.md"].size > 0


def test_cat_returns_metadata_and_body(memory_fs):
    _seed(memory_fs)
    res = memory_fs.cat("/people/emily.md")
    assert res.metadata["title"] == "Emily"
    assert "Emily likes coffee" in res.content


def test_cat_missing_raises(memory_fs):
    with pytest.raises(FileNotFoundError):
        memory_fs.cat("/people/nobody.md")


def test_grep_literal(memory_fs):
    _seed(memory_fs)
    matches = memory_fs.grep("payments")
    assert len(matches) == 1
    assert matches[0].path == "/people/john.md"


def test_grep_ignore_case_and_scope(memory_fs):
    _seed(memory_fs)
    assert memory_fs.grep("FRIDAY") == []
    matches = memory_fs.grep("FRIDAY", path="/tasks", ignore_case=True)
    assert len(matches) == 1
    assert matches[0].line_number >= 1


def test_grep_regex_with_context(memory_fs):
    _seed(memory_fs)
    matches = memory_fs.grep(r"Q\d report", path="/", regex=True, ignore_case=True, context=1)
    assert len(matches) == 1
    assert matches[0].path == "/tasks/open-items.md"
