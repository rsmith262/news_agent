from __future__ import annotations

import html
import re
import time
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime

import feedparser


_TAG_STRIP_RE = re.compile(r"<[^>]+>")
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/133.0.0.0 Safari/537.36 NewsAgent/0.1"
)


@dataclass
class FeedItem:
    title: str
    link: str
    summary: str
    source: str
    feed_url: str
    published_at: datetime | None


def _clean_html(text: str | None) -> str:
    if not text:
        return ""
    return html.unescape(_TAG_STRIP_RE.sub("", text)).strip()


def _parse_date(entry) -> datetime | None:
    published_parsed = getattr(entry, "published_parsed", None)
    if published_parsed is not None:
        try:
            return datetime.fromtimestamp(time.mktime(published_parsed))
        except (OverflowError, ValueError, OSError):
            pass

    updated_parsed = getattr(entry, "updated_parsed", None)
    if updated_parsed is not None:
        try:
            return datetime.fromtimestamp(time.mktime(updated_parsed))
        except (OverflowError, ValueError, OSError):
            pass

    for field in ("published", "updated"):
        raw = getattr(entry, field, "") or ""
        if not raw:
            continue
        try:
            return parsedate_to_datetime(raw)
        except (TypeError, ValueError):
            continue

    return None


def parse_feed(url: str) -> list[FeedItem]:
    try:
        feed = feedparser.parse(url, agent=USER_AGENT)
    except Exception:
        return []

    entries = getattr(feed, "entries", []) or []
    source = getattr(getattr(feed, "feed", None), "title", "") or url

    items: list[FeedItem] = []
    for entry in entries:
        title = _clean_html(getattr(entry, "title", ""))
        link = (getattr(entry, "link", "") or "").strip()
        summary = _clean_html(getattr(entry, "summary", "") or getattr(entry, "description", ""))

        if not title or not link:
            continue

        items.append(
            FeedItem(
                title=title,
                link=link,
                summary=summary,
                source=source,
                feed_url=url,
                published_at=_parse_date(entry),
            )
        )

    return items
