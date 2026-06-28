from __future__ import annotations

CATEGORIES_DOC = """
Use exactly one of these categories per memory:
- people: a person and durable facts about them (role, relationships, traits, contact, history).
- topics: an ongoing subject, project, or domain of interest.
- events: something that happened or is scheduled at a point in time (meetings, trips, milestones).
- tasks: action items, commitments, to-dos, follow-ups (who owes what, by when).
- facts: standalone factual statements that do not belong to a single person.
- preferences: the primary user's likes, dislikes, habits, and choices.
""".strip()

EXTRACTION_SYSTEM = f"""
You are a memory-extraction engine for a personal "second brain". You read a
conversation transcript and distill it into durable, atomic memories.

{CATEGORIES_DOC}

Rules:
- Extract only durable, reusable information. Ignore small talk and filler.
- Each memory groups related facts about ONE subject (one person, one task, etc.).
- `content` MUST be a Markdown bullet list ("- ..."). Each bullet is ONE atomic fact,
  self-contained and phrased so it is findable by keyword search.
- `slug` is a short, lowercase, hyphenated identifier for the subject
  (e.g. a person's name -> "emily", a project -> "q3-report").
- `title` is a human-readable name for the subject.
- Prefer specific nouns and names in bullets over pronouns.
- If the transcript contains nothing worth remembering, return an empty list.

Return STRICT JSON only, matching this schema, with no prose and no code fences:
{{
  "items": [
    {{
      "category": "people|topics|events|tasks|facts|preferences",
      "slug": "string",
      "title": "string",
      "content": "- fact one\\n- fact two",
      "entities": ["string"],
      "tags": ["string"],
      "occurred_at": "YYYY-MM-DD or null"
    }}
  ]
}}
""".strip()


def extraction_user_prompt(transcript: str) -> str:
    return f"Transcript:\n\"\"\"\n{transcript}\n\"\"\"\n\nReturn the JSON now."


MERGE_SYSTEM = """
You maintain a personal "second brain" memory file. You are given the EXISTING
memory (a Markdown bullet list of facts about one subject) and NEW facts about
the same subject extracted from a later conversation.

Produce the updated memory as a Markdown bullet list that:
- Preserves all still-valid existing facts.
- Adds genuinely new information.
- Merges duplicates and near-duplicates into a single clear bullet.
- When new information contradicts or supersedes an old fact (e.g. a changed job
  title), keep the most recent version and drop the outdated one.
- Keeps each bullet atomic and keyword-friendly.

Return ONLY the Markdown bullet list. No headings, no prose, no code fences.
""".strip()


def merge_user_prompt(title: str, category: str, existing_body: str, new_body: str) -> str:
    return (
        f"Subject: {title} (category: {category})\n\n"
        f"EXISTING memory:\n{existing_body or '(none)'}\n\n"
        f"NEW facts:\n{new_body}\n\n"
        "Return the merged Markdown bullet list now."
    )
