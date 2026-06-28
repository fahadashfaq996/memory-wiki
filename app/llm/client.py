from __future__ import annotations

import json
import re
from typing import Protocol

from app.config import Settings, get_settings
from app.llm import prompts
from app.schemas.memory import MemoryExtraction, MemoryItem, slugify


class LLMError(RuntimeError):
    pass


class MemoryLLM(Protocol):
    def extract(self, transcript: str) -> MemoryExtraction: ...

    def merge(self, *, title: str, category: str, existing_body: str, new_body: str) -> str: ...


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9]*\n", "", text)
        text = re.sub(r"\n```$", "", text)
    return text.strip()


def _parse_extraction(raw: str) -> MemoryExtraction:
    cleaned = _strip_code_fences(raw)
    # Be liberal: some models wrap JSON in prose. Grab the outermost object.
    if not cleaned.startswith("{"):
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            cleaned = match.group(0)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise LLMError(f"LLM returned invalid JSON: {exc}") from exc
    return MemoryExtraction.model_validate(data)


class OpenRouterLLM:
    def __init__(self, settings: Settings | None = None):
        from openai import OpenAI  # imported lazily so tests need not install it

        self.settings = settings or get_settings()
        if not self.settings.openrouter_api_key:
            raise LLMError("OPENROUTER_API_KEY is not set (or use LLM_PROVIDER=fake).")
        self._client = OpenAI(
            api_key=self.settings.openrouter_api_key,
            base_url=self.settings.openrouter_base_url,
            timeout=self.settings.llm_request_timeout,
        )
        self.model = self.settings.llm_model

    def _chat(self, system: str, user: str) -> str:
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
        )
        return resp.choices[0].message.content or ""

    def extract(self, transcript: str) -> MemoryExtraction:
        raw = self._chat(prompts.EXTRACTION_SYSTEM, prompts.extraction_user_prompt(transcript))
        return _parse_extraction(raw)

    def merge(self, *, title: str, category: str, existing_body: str, new_body: str) -> str:
        raw = self._chat(
            prompts.MERGE_SYSTEM,
            prompts.merge_user_prompt(title, category, existing_body, new_body),
        )
        return _strip_code_fences(raw)


class FakeLLM:
    """Deterministic, dependency-free LLM stub.

    Extraction heuristics:
    - "Name: utterance" speaker lines -> one `people` memory per speaker.
    - Lines mentioning task-like verbs -> `tasks` memories.
    Merge: union of bullet lines, de-duplicated, order preserved.
    """

    _SPEAKER_RE = re.compile(r"^\s*([A-Z][A-Za-z0-9 ._-]{0,40}?):\s*(.+)$")
    _TASK_RE = re.compile(r"\b(will|i'?ll|need to|should|to-?do|follow up|send|finish|by friday|deadline)\b", re.I)

    def extract(self, transcript: str) -> MemoryExtraction:
        people: dict[str, list[str]] = {}
        tasks: list[str] = []
        order: list[str] = []

        for line in transcript.splitlines():
            m = self._SPEAKER_RE.match(line)
            if not m:
                continue
            speaker, utterance = m.group(1).strip(), m.group(2).strip()
            if speaker not in people:
                people[speaker] = []
                order.append(speaker)
            people[speaker].append(utterance)
            if self._TASK_RE.search(utterance):
                tasks.append(f"{speaker}: {utterance}")

        items: list[MemoryItem] = []
        for speaker in order:
            bullets = "\n".join(f"- {speaker} said: {u}" for u in people[speaker])
            items.append(
                MemoryItem(
                    category="people",
                    slug=slugify(speaker),
                    title=speaker,
                    content=bullets,
                    entities=[speaker],
                    tags=["speaker"],
                )
            )
        if tasks:
            bullets = "\n".join(f"- {t}" for t in tasks)
            items.append(
                MemoryItem(
                    category="tasks",
                    slug="open-items",
                    title="Open Items",
                    content=bullets,
                    tags=["task"],
                )
            )
        return MemoryExtraction(items=items)

    def merge(self, *, title: str, category: str, existing_body: str, new_body: str) -> str:
        seen: set[str] = set()
        merged: list[str] = []
        for block in (existing_body, new_body):
            for line in block.splitlines():
                stripped = line.strip()
                if not stripped:
                    continue
                if stripped not in seen:
                    seen.add(stripped)
                    merged.append(stripped if stripped.startswith("-") else f"- {stripped}")
        return "\n".join(merged)


def get_memory_llm(settings: Settings | None = None) -> MemoryLLM:
    settings = settings or get_settings()
    if settings.llm_is_fake:
        return FakeLLM()
    return OpenRouterLLM(settings)
