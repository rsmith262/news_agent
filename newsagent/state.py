from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AgentState:
    posted_urls: set[str] = field(default_factory=set)


def load_state(path: Path) -> AgentState:
    if not path.exists():
        return AgentState()

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return AgentState()

    urls = raw.get("posted_urls", []) if isinstance(raw, dict) else []
    if not isinstance(urls, list):
        urls = []

    return AgentState(posted_urls={str(u).strip().lower() for u in urls if str(u).strip()})


def save_state(path: Path, state: AgentState) -> None:
    payload = {"posted_urls": sorted(state.posted_urls)}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
