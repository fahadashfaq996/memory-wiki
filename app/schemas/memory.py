from __future__ import annotations

import datetime
import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Category = Literal["people", "topics", "events", "tasks", "facts", "preferences"]

CATEGORIES: tuple[str, ...] = ("people", "topics", "events", "tasks", "facts", "preferences")

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    """Normalize an arbitrary string into a filesystem-safe slug."""
    value = value.strip().lower()
    value = _SLUG_RE.sub("-", value)
    value = value.strip("-")
    return value or "untitled"


class MemoryItem(BaseModel):
    """A single atomic memory the LLM extracts from a transcript."""

    category: Category
    slug: str
    title: str
    content: str = Field(description="Markdown bullet list of atomic facts.")
    entities: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    occurred_at: str | None = None

    @field_validator("slug")
    @classmethod
    def _normalize_slug(cls, v: str) -> str:
        return slugify(v)


class MemoryExtraction(BaseModel):
    items: list[MemoryItem] = Field(default_factory=list)


# --- Filesystem-style API responses ---


class DirEntry(BaseModel):
    name: str
    path: str
    type: Literal["dir", "file"]
    size: int | None = None
    updated_at: datetime.datetime | None = None


class LsResponse(BaseModel):
    path: str
    entries: list[DirEntry]


class CatResponse(BaseModel):
    path: str
    metadata: dict
    content: str


class GrepMatch(BaseModel):
    path: str
    line_number: int
    line: str
    context_before: list[str] = Field(default_factory=list)
    context_after: list[str] = Field(default_factory=list)


class GrepResponse(BaseModel):
    query: str
    path: str
    match_count: int
    matches: list[GrepMatch]
