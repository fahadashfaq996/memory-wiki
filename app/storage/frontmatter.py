"""Parse and render Markdown files with YAML frontmatter.

Memory files are stored as::

    ---
    title: Emily
    category: people
    ...
    ---
    - bullet facts

Keeping this in one small, well-tested module avoids subtle serialization bugs.
"""

from __future__ import annotations

import yaml

_DELIM = "---"


def dumps(metadata: dict, body: str) -> str:
    front = yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True).rstrip("\n")
    body = body.rstrip("\n")
    return f"{_DELIM}\n{front}\n{_DELIM}\n\n{body}\n"


def loads(text: str) -> tuple[dict, str]:
    """Return (metadata, body). Tolerates files without frontmatter."""
    if not text.startswith(_DELIM):
        return {}, text.strip("\n")

    lines = text.split("\n")
    closing = None
    for i in range(1, len(lines)):
        if lines[i].strip() == _DELIM:
            closing = i
            break
    if closing is None:
        return {}, text.strip("\n")

    front_block = "\n".join(lines[1:closing])
    body = "\n".join(lines[closing + 1 :]).strip("\n")
    metadata = yaml.safe_load(front_block) or {}
    if not isinstance(metadata, dict):
        metadata = {}
    return metadata, body
