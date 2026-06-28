from __future__ import annotations

from app.llm.client import MemoryLLM
from app.schemas.memory import MemoryExtraction


def extract_memories(llm: MemoryLLM, transcript: str) -> MemoryExtraction:
    if not transcript or not transcript.strip():
        return MemoryExtraction(items=[])
    return llm.extract(transcript)
