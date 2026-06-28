import pytest

moto = pytest.importorskip("moto")
from moto import mock_aws

from app.config import Settings
from app.storage import frontmatter
from app.storage.memory_fs import MemoryFS
from app.storage.object_store import ObjectNotFound, ObjectStore

pytestmark = pytest.mark.integration


def _settings() -> Settings:
    return Settings(
        s3_endpoint_url=None,
        s3_access_key="testing",
        s3_secret_key="testing",
        s3_region="us-east-1",
        s3_bucket="test-memories",
        memory_prefix="memories",
    )


@mock_aws
def test_object_store_put_get_list_delete():
    store = ObjectStore(_settings())
    store.ensure_bucket()

    store.put("memories/people/emily.md", "hello", metadata={"x": "y"})
    assert store.exists("memories/people/emily.md")
    assert store.get("memories/people/emily.md") == "hello"

    common, objects = store.list("memories/", delimiter="/")
    assert "memories/people/" in common

    store.delete("memories/people/emily.md")
    with pytest.raises(ObjectNotFound):
        store.get("memories/people/emily.md")


@mock_aws
def test_memory_fs_ls_cat_grep_against_s3():
    settings = _settings()
    store = ObjectStore(settings)
    store.ensure_bucket()
    fs = MemoryFS(store=store, settings=settings)

    fs.write_raw("people/john.md", frontmatter.dumps({"title": "John"}, "- John joined payments"))
    fs.write_raw("tasks/open-items.md", frontmatter.dumps({"title": "Open"}, "- Send Q3 report Friday"))

    root = {e.name for e in fs.ls("/").entries}
    assert {"people", "tasks"} <= root

    cat = fs.cat("/people/john.md")
    assert cat.metadata["title"] == "John"

    matches = fs.grep("payments")
    assert len(matches) == 1 and matches[0].path == "/people/john.md"
