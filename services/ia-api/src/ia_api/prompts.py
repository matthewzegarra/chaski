"""Versioned prompts in genai/prompts/*.md with a front-matter (id, version, owner)."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ia_api.settings import get_settings

REQUIRED = ("id", "version", "owner")


@dataclass(frozen=True)
class Prompt:
    id: str
    version: str
    owner: str
    description: str
    text: str


def parse_prompt(raw: str) -> Prompt:
    if not raw.startswith("---"):
        raise ValueError("Prompt file must start with a front-matter block")
    _, header, body = raw.split("---", 2)
    meta: dict[str, str] = {}
    for line in header.strip().splitlines():
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()
    missing = [k for k in REQUIRED if not meta.get(k)]
    if missing:
        raise ValueError(f"Prompt front-matter is missing: {', '.join(missing)}")
    return Prompt(
        id=meta["id"],
        version=meta["version"],
        owner=meta["owner"],
        description=meta.get("description", ""),
        text=body.strip(),
    )


@lru_cache
def load_prompt(prompt_id: str) -> Prompt:
    path = Path(get_settings().prompts_dir) / f"{prompt_id}.md"
    prompt = parse_prompt(path.read_text(encoding="utf-8"))
    if prompt.id != prompt_id:
        raise ValueError(f"{path.name}: front-matter id {prompt.id!r} does not match the file name")
    return prompt
