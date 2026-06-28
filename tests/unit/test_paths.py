import pytest

from app.schemas.memory import slugify
from app.storage.memory_fs import InvalidPath, normalize_path

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Emily", "emily"),
        ("  Q3 Report!! ", "q3-report"),
        ("payments_group", "payments-group"),
        ("***", "untitled"),
    ],
)
def test_slugify(raw, expected):
    assert slugify(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("/", ""),
        ("", ""),
        ("/people", "people"),
        ("people/", "people"),
        ("/people/emily.md", "people/emily.md"),
        ("//people//emily.md", "people/emily.md"),
    ],
)
def test_normalize_path_ok(raw, expected):
    assert normalize_path(raw) == expected


@pytest.mark.parametrize("raw", ["../etc/passwd", "/people/../../secret", "people/$(rm)", "a/b/../c"])
def test_normalize_path_rejects_traversal(raw):
    with pytest.raises(InvalidPath):
        normalize_path(raw)
