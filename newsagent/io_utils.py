from __future__ import annotations

from pathlib import Path


def load_lines(path: Path) -> list[str]:
    if not path.exists():
        return []

    lines: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        clean = line.lstrip("\ufeff").strip()
        if not clean or clean.startswith("#"):
            continue
        lines.append(clean)
    return lines


def load_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()
