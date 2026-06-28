"""The memory file tree: a navigable filesystem backed by object storage.

Logical paths (what the API speaks) look like::

    /                      -> the tree root
    /people                -> a directory
    /people/emily.md    -> a memory file

These map onto object keys under ``<memory_prefix>/...`` in the bucket. This
module is the single place that knows that mapping, enforces path safety, and
implements ``ls`` / ``cat`` / ``grep`` plus memory writes.
"""

from __future__ import annotations

import re

from app.config import Settings, get_settings
from app.schemas.memory import CatResponse, DirEntry, GrepMatch, LsResponse
from app.storage import frontmatter
from app.storage.object_store import ObjectNotFound, ObjectStore


class InvalidPath(ValueError):
    """Raised when a caller-supplied path is unsafe or malformed."""


class NotAFile(ValueError):
    pass


_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9._-]+$")


def normalize_path(path: str) -> str:
    """Validate and normalize a logical path to a clean relative form.

    Returns "" for the root, otherwise a slash-joined relative path with no
    leading/trailing slashes. Rejects traversal (``..``) and odd characters.
    """
    if path is None:
        return ""
    path = path.strip()
    if path in ("", "/", "."):
        return ""
    segments = [seg for seg in path.split("/") if seg != ""]
    for seg in segments:
        if seg in (".", "..") or not _SAFE_SEGMENT.match(seg):
            raise InvalidPath(f"Unsafe path segment: {seg!r}")
    return "/".join(segments)


class MemoryFS:
    def __init__(self, store: ObjectStore | None = None, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.store = store or ObjectStore(self.settings)
        self.prefix = self.settings.memory_prefix.strip("/")


    def _key(self, rel: str) -> str:
        return f"{self.prefix}/{rel}" if rel else f"{self.prefix}/"

    def _to_logical(self, key: str) -> str:
        rel = key[len(self.prefix) + 1 :] if key.startswith(self.prefix + "/") else key
        return "/" + rel

    # --- operations ---

    def ls(self, path: str) -> LsResponse:
        rel = normalize_path(path)
        prefix = self._key(rel)
        if rel and not prefix.endswith("/"):
            prefix += "/"
        common_prefixes, objects = self.store.list(prefix, delimiter="/")

        entries: list[DirEntry] = []
        for cp in sorted(common_prefixes):
            name = cp[len(prefix) :].rstrip("/")
            entries.append(DirEntry(name=name, path=self._to_logical(cp.rstrip("/")), type="dir"))
        for obj in sorted(objects, key=lambda o: o.key):
            name = obj.key[len(prefix) :]
            if not name:  # the directory placeholder key itself
                continue
            entries.append(
                DirEntry(
                    name=name,
                    path=self._to_logical(obj.key),
                    type="file",
                    size=obj.size,
                    updated_at=obj.last_modified,
                )
            )
        return LsResponse(path="/" + rel if rel else "/", entries=entries)

    def cat(self, path: str) -> CatResponse:
        rel = normalize_path(path)
        if not rel:
            raise NotAFile("Cannot cat the root directory")
        key = self._key(rel)
        try:
            raw = self.store.get(key)
        except ObjectNotFound as exc:
            raise FileNotFoundError(path) from exc
        metadata, body = frontmatter.loads(raw)
        return CatResponse(path="/" + rel, metadata=metadata, content=body)

    def read_raw(self, rel: str) -> str | None:
        """Return raw file text for an already-normalized rel path, or None."""
        try:
            return self.store.get(self._key(rel))
        except ObjectNotFound:
            return None

    def write_raw(self, rel: str, text: str) -> None:
        self.store.put(self._key(rel), text)

    def grep(
        self,
        query: str,
        path: str = "",
        *,
        ignore_case: bool = False,
        regex: bool = False,
        context: int = 0,
        max_results: int = 200,
    ) -> list[GrepMatch]:
        rel = normalize_path(path)
        prefix = self._key(rel)
        if rel and not prefix.endswith("/"):
            prefix += "/"

        flags = re.IGNORECASE if ignore_case else 0
        pattern = re.compile(query if regex else re.escape(query), flags)

        _, objects = self.store.list(prefix, delimiter=None)
        matches: list[GrepMatch] = []
        for obj in sorted(objects, key=lambda o: o.key):
            if obj.key.endswith("/"):
                continue
            try:
                text = self.store.get(obj.key)
            except ObjectNotFound:
                continue
            lines = text.split("\n")
            for idx, line in enumerate(lines):
                if pattern.search(line):
                    matches.append(
                        GrepMatch(
                            path=self._to_logical(obj.key),
                            line_number=idx + 1,
                            line=line,
                            context_before=lines[max(0, idx - context) : idx] if context else [],
                            context_after=lines[idx + 1 : idx + 1 + context] if context else [],
                        )
                    )
                    if len(matches) >= max_results:
                        return matches
        return matches
