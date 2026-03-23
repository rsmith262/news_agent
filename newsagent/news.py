from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .rss import FeedItem, parse_feed


@dataclass
class SearchRequest:
    topic: str | None
    retrieval_framing: str | None
    feed_hint: str | None
    today_only: bool


FRAMING_TERMS: dict[str, list[str]] = {
    "positive": [
        "benefit",
        "benefits",
        "positive",
        "improvement",
        "improvements",
        "success",
        "breakthrough",
        "adoption",
        "growth",
        "opportunity",
        "helpful",
        "useful",
    ],
    "critical": [
        "critical",
        "skeptical",
        "concern",
        "concerns",
        "backlash",
        "controversy",
        "controversial",
        "lawsuit",
        "problem",
        "problems",
        "risk",
        "risks",
        "warning",
        "warnings",
        "critic",
        "criticism",
    ],
    "risk": [
        "risk",
        "risks",
        "safety",
        "harm",
        "harms",
        "misuse",
        "bias",
        "security",
        "threat",
        "warning",
        "warnings",
        "danger",
        "dangerous",
    ],
}


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _term_matches(haystack: str, term: str) -> bool:
    t = term.lower().strip()
    if not t:
        return False
    return re.search(rf"(?<!\w){re.escape(t)}(?!\w)", haystack) is not None


def _count_hits(haystack: str, terms: list[str]) -> int:
    hits = 0
    for term in terms:
        if _term_matches(haystack, term):
            hits += 1
    return hits


def _topic_terms(topic: str | None, default_keywords: list[str]) -> list[str]:
    if not topic:
        return default_keywords

    parts = [p.strip() for p in re.split(r"[,/]|\band\b", topic, flags=re.IGNORECASE) if p.strip()]
    terms = [t.lower() for t in parts]

    if topic.lower() not in terms:
        terms.append(topic.lower())

    # If the user gave a topic, focus ranking on that topic instead of broad defaults.
    return list(dict.fromkeys(terms))


def _framing_terms(framing: str | None) -> list[str]:
    if not framing:
        return []

    lowered = framing.lower().strip()
    terms: list[str] = []
    for key, values in FRAMING_TERMS.items():
        if key in lowered:
            terms.extend(values)

    if not terms and lowered:
        terms.append(lowered)

    return list(dict.fromkeys(terms))


def _score_item(item: FeedItem, terms: list[str], now_local: datetime, tz: ZoneInfo) -> tuple[int, int]:
    haystack = _clean(f"{item.title} {item.summary}")
    score = 0
    hits = _count_hits(haystack, terms)

    for term in terms:
        if _term_matches(haystack, term):
            score += 3

    if item.published_at:
        dt = item.published_at.astimezone(tz) if item.published_at.tzinfo else item.published_at.replace(tzinfo=tz)
        hours_old = max((now_local - dt).total_seconds() / 3600.0, 0)
        score += max(0, int(36 - hours_old))

    return score, hits


def _matches_feed_hint(item: FeedItem, hint: str | None) -> bool:
    if not hint:
        return True
    h = hint.lower().strip()
    if not h:
        return True

    return h in item.source.lower() or h in item.feed_url.lower()


def _matches_date(item: FeedItem, today_only: bool, now_local: datetime, tz: ZoneInfo) -> bool:
    if item.published_at is None:
        return not today_only

    local_dt = item.published_at.astimezone(tz) if item.published_at.tzinfo else item.published_at.replace(tzinfo=tz)
    if today_only:
        return local_dt.date() == now_local.date()

    return local_dt >= now_local - timedelta(hours=72)


def fetch_ranked_news(
    feed_urls: list[str],
    request: SearchRequest,
    default_keywords: list[str],
    timezone_name: str,
) -> list[FeedItem]:
    tz = ZoneInfo(timezone_name)
    now_local = datetime.now(tz)
    terms = _topic_terms(request.topic, default_keywords)
    framing_terms = _framing_terms(request.retrieval_framing)
    ai_terms = [k.lower().strip() for k in default_keywords if k.strip()]

    scored: list[tuple[int, FeedItem]] = []
    seen_links: set[str] = set()

    for url in feed_urls:
        for item in parse_feed(url):
            link_key = item.link.strip().lower()
            if not link_key or link_key in seen_links:
                continue

            if not _matches_feed_hint(item, request.feed_hint):
                continue

            if not _matches_date(item, request.today_only, now_local, tz):
                continue

            haystack = _clean(f"{item.title} {item.summary}")
            # Hard AI-only gate: must match at least one default AI keyword.
            if _count_hits(haystack, ai_terms) == 0:
                continue

            score, hits = _score_item(item, terms, now_local, tz)
            # Enforce AI/topic relevance: at least one keyword hit is required.
            if hits == 0:
                continue
            if framing_terms:
                framing_hits = _count_hits(haystack, framing_terms)
                if framing_hits == 0:
                    continue
                score += framing_hits * 3
            if score <= 0:
                continue

            seen_links.add(link_key)
            scored.append((score, item))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored]
