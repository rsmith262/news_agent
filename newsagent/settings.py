from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    openai_model: str
    timezone: str
    dry_run: bool
    state_file: Path
    feeds_file: Path
    keywords_file: Path
    policy_file: Path
    max_candidates: int


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_settings(base_dir: Path | None = None) -> Settings:
    root = base_dir or Path.cwd()
    load_dotenv(root / ".env")

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("OPENAI_API_KEY is missing in .env")

    return Settings(
        openai_api_key=api_key,
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip(),
        timezone=os.getenv("NEWSAGENT_TZ", "Europe/London").strip(),
        dry_run=_as_bool(os.getenv("DRY_RUN"), default=True),
        state_file=root / ".newsagent_state.json",
        feeds_file=root / "config" / "feeds.txt",
        keywords_file=root / "config" / "keywords.txt",
        policy_file=root / "config" / "posting_policy.md",
        max_candidates=int(os.getenv("MAX_CANDIDATES", "3")),
    )
