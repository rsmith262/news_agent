from __future__ import annotations

from dataclasses import dataclass

import httpx

from .agent import DraftCandidate, NewsAgent
from .llm import Intent
from .settings import Settings, load_settings

BLOCKED_TERMS: tuple[str, ...] = (
    "adult",
    "porn",
    "pornography",
    "sexual",
    "sexually explicit",
    "onlyfans",
    "nude",
    "nudity",
    "escort",
    "escorting",
    "illegal",
    "fraud",
    "scam",
    "money laundering",
    "drug trafficking",
    "weapon",
    "weapons",
    "extremist",
    "terror",
    "terrorism",
    "csam",
    "child sexual abuse",
    "exploit kit",
    "malware campaign",
)


@dataclass
class AutopostOutcome:
    posted: bool
    message: str


def _candidate_text(candidate: DraftCandidate) -> str:
    item = candidate.item
    if item is None:
        return candidate.context
    return "\n".join((item.title, item.summary, item.source, item.link))


def _fails_hard_safety(candidate: DraftCandidate) -> str | None:
    haystack = _candidate_text(candidate).lower()
    for term in BLOCKED_TERMS:
        if term in haystack:
            return f"blocked by hard safety term: {term}"
    return None


def _send_telegram_message(settings: Settings, text: str) -> None:
    if not settings.telegram_bot_token or settings.telegram_chat_id is None:
        print(text)
        return

    with httpx.Client(timeout=30.0) as client:
        client.post(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
            json={
                "chat_id": settings.telegram_chat_id,
                "text": text,
                "disable_web_page_preview": True,
            },
        ).raise_for_status()


def run_autopost() -> AutopostOutcome:
    settings = load_settings()
    agent = NewsAgent(settings)
    intent = Intent(kind="news")
    candidates, reason = agent._build_news_candidates(intent)

    if not candidates:
        if reason == "deduped_only":
            message = "Daily autopost skipped: matching stories existed, but they were all deduped."
        else:
            message = "Daily autopost skipped: no matching broad AI stories were found."
        _send_telegram_message(settings, message)
        return AutopostOutcome(posted=False, message=message)

    chosen: DraftCandidate | None = None
    safety_reason = "no safe candidate found"

    for candidate in candidates:
        hard_fail = _fails_hard_safety(candidate)
        if hard_fail:
            safety_reason = hard_fail
            continue
        item = candidate.item
        if item is None:
            continue
        decision = agent.llm.assess_autopost_safety(
            policy_text=agent.policy_text,
            title=item.title,
            summary=item.summary,
            source=item.source,
        )
        if not decision.allow:
            safety_reason = decision.reason
            continue
        chosen = candidate
        break

    if chosen is None:
        message = f"Daily autopost skipped after safety review: {safety_reason}"
        _send_telegram_message(settings, message)
        return AutopostOutcome(posted=False, message=message)

    result = agent.poster.post(chosen.draft, topic_tag=chosen.topic_tag)
    if result.posted:
        agent._save_posted_item(chosen)

    summary = [
        "Daily autopost result:",
        f"Source: {chosen.item.source if chosen.item else 'n/a'}",
        f"Title: {chosen.item.title if chosen.item else 'n/a'}",
        f"Topic tag: {chosen.topic_tag or 'None'}",
        result.message,
    ]
    _send_telegram_message(settings, "\n".join(summary))
    return AutopostOutcome(posted=result.posted, message=result.message)


if __name__ == "__main__":
    outcome = run_autopost()
    print(outcome.message)
