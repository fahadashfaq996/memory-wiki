from __future__ import annotations

import datetime

from app.llm.client import MemoryLLM
from app.schemas.memory import MemoryExtraction, MemoryItem
from app.storage import frontmatter
from app.storage.memory_fs import MemoryFS


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _rel_path(item: MemoryItem) -> str:
    return f"{item.category}/{item.slug}.md"


def _union(*lists: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for lst in lists:
        for v in lst or []:
            if v not in seen:
                seen.add(v)
                out.append(v)
    return out


def merge_into_tree(
    fs: MemoryFS,
    llm: MemoryLLM,
    extraction: MemoryExtraction,
    transcript_id: str,
) -> list[str]:
    """Apply an extraction to the tree. Returns the logical paths written."""
    written: list[str] = []
    for item in extraction.items:
        rel = _rel_path(item)
        existing_raw = fs.read_raw(rel)
        now = _now_iso()

        if existing_raw is None:
            metadata = {
                "title": item.title,
                "category": item.category,
                "tags": item.tags,
                "entities": item.entities,
                "source_transcripts": [transcript_id],
                "occurred_at": item.occurred_at,
                "created_at": now,
                "updated_at": now,
            }
            body = item.content.strip()
        else:
            meta, old_body = frontmatter.loads(existing_raw)
            sources = list(meta.get("source_transcripts", []) or [])
            if transcript_id in sources:
                # Already incorporated this transcript -> idempotent no-op.
                continue
            merged_body = llm.merge(
                title=item.title,
                category=item.category,
                existing_body=old_body,
                new_body=item.content.strip(),
            ).strip()
            metadata = {
                "title": meta.get("title", item.title),
                "category": item.category,
                "tags": _union(meta.get("tags", []), item.tags),
                "entities": _union(meta.get("entities", []), item.entities),
                "source_transcripts": sources + [transcript_id],
                "occurred_at": meta.get("occurred_at") or item.occurred_at,
                "created_at": meta.get("created_at", now),
                "updated_at": now,
            }
            body = merged_body

        fs.write_raw(rel, frontmatter.dumps(metadata, body))
        written.append("/" + rel)
    return written
