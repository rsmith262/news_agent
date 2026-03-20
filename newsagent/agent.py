from __future__ import annotations

import re
from dataclasses import dataclass

from .io_utils import load_lines, load_text
from .llm import Intent, LLM, RevisionIntent
from .news import SearchRequest, fetch_ranked_news
from .rss import FeedItem
from .settings import Settings
from .state import AgentState, load_state, save_state
from .threads_client import ThreadsPoster


@dataclass
class DraftCandidate:
    item: FeedItem | None
    draft: str
    mode: str
    context: str


DEFAULT_HASHTAGS = ("#ArtificialIntelligence", "#AI")
BRAND_HASHTAGS: tuple[tuple[str, str], ...] = (
    ("openai", "#OpenAI"),
    ("chatgpt", "#ChatGPT"),
    ("anthropic", "#Anthropic"),
    ("claude", "#Claude"),
    ("gemini", "#Gemini"),
)
CONTEXT_HASHTAGS: tuple[tuple[str, str], ...] = (
    ("llm", "#LLM"),
    ("agent", "#AIAgents"),
    ("agents", "#AIAgents"),
    ("machine learning", "#MachineLearning"),
    ("model", "#GenAI"),
    ("models", "#GenAI"),
    ("generative", "#GenAI"),
    ("genai", "#GenAI"),
)


class NewsAgent:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.state: AgentState = load_state(settings.state_file)
        self.llm = LLM(api_key=settings.openai_api_key, model=settings.openai_model)
        self.poster = ThreadsPoster(dry_run=settings.dry_run)
        self.feed_urls = load_lines(settings.feeds_file)
        self.default_keywords = load_lines(settings.keywords_file)
        self.policy_text = load_text(settings.policy_file)
        self.pending_candidates: list[DraftCandidate] = []
        self.current_index = 0

    def _filter_deduped(self, items: list[FeedItem]) -> list[FeedItem]:
        filtered: list[FeedItem] = []
        for item in items:
            key = item.link.strip().lower()
            if key in self.state.posted_urls:
                continue
            filtered.append(item)
        return filtered

    def _build_news_candidates(self, intent: Intent) -> list[DraftCandidate]:
        items = fetch_ranked_news(
            feed_urls=self.feed_urls,
            request=SearchRequest(
                topic=intent.topic,
                retrieval_framing=intent.retrieval_framing,
                feed_hint=intent.feed_hint,
                today_only=intent.today_only,
            ),
            default_keywords=self.default_keywords,
            timezone_name=self.settings.timezone,
        )
        items = self._filter_deduped(items)
        if not items:
            return []

        candidates: list[DraftCandidate] = []
        for item in items[: self.settings.max_candidates]:
            blurb = self.llm.draft_news_post(
                policy_text=self.policy_text,
                title=item.title,
                summary=item.summary,
                source=item.source,
                topic=intent.topic,
                writing_angle=intent.writing_angle,
            )
            # Force grounded output with canonical feed link appended.
            draft = f"{blurb.rstrip()}\n\n{item.link}"
            context = (
                f"Mode: news\n"
                f"Retrieval framing: {intent.retrieval_framing or 'None'}\n"
                f"Writing angle: {intent.writing_angle or 'None'}\n"
                f"Source: {item.source}\n"
                f"Title: {item.title}\n"
                f"Summary: {item.summary}\n"
                f"Link: {item.link}"
            )
            candidate = DraftCandidate(item=item, draft=draft, mode="news", context=context)
            candidate.draft = self._normalize_candidate_draft(candidate, candidate.draft)
            candidates.append(candidate)

        return candidates

    def _build_analysis_candidates(self, user_text: str) -> list[DraftCandidate]:
        draft = self.llm.draft_analysis_post(self.policy_text, user_text)
        candidate = DraftCandidate(
            item=None,
            draft=draft,
            mode="analysis",
            context=f"Mode: analysis\nOriginal request: {user_text}",
        )
        candidate.draft = self._normalize_candidate_draft(candidate, candidate.draft)
        return [candidate]

    def _build_explainer_candidates(self, user_text: str) -> list[DraftCandidate]:
        draft = self.llm.draft_explainer_post(self.policy_text, user_text)
        candidate = DraftCandidate(
            item=None,
            draft=draft,
            mode="explain",
            context=f"Mode: explain\nOriginal request: {user_text}",
        )
        candidate.draft = self._normalize_candidate_draft(candidate, candidate.draft)
        return [candidate]

    def handle_new_request(self, user_text: str) -> str:
        intent = self.llm.parse_intent(user_text)

        if intent.kind == "news":
            candidates = self._build_news_candidates(intent)
        elif intent.kind == "analysis":
            candidates = self._build_analysis_candidates(user_text)
        elif intent.kind == "explain":
            candidates = self._build_explainer_candidates(user_text)
        elif intent.kind == "help":
            return self.help_text()
        else:
            return (
                "I could not classify that request. Ask for news, analysis, or an explainer.\n"
                "Example: 'Can you post me a news story about OpenAI from today?'"
            )

        if not candidates:
            self.pending_candidates = []
            self.current_index = 0
            return "No matching deduped stories found for that request. Try another topic/feed/date filter."

        self.pending_candidates = candidates
        self.current_index = 0
        return self._render_current_candidate()

    def help_text(self) -> str:
        return (
            "Try natural language requests like:\n"
            "- 'Can you post me a news story?'\n"
            "- 'Can you post me a news story from today?'\n"
            "- 'Can you post me a news story about Claude from Anthropic?'\n"
            "- 'Post me a story highlighting the risks of AI.'\n"
            "- 'Write me a post analysing AI agents in customer support.'\n"
            "- 'Explain retrieval-augmented generation in one post.'\n\n"
            "Once I show a draft, you can reply with:\n"
            "- 'approve'\n"
            "- 'another'\n"
            "- 'make it shorter'\n"
            "- 'make it more critical'\n"
            "- 'give it more opinion'\n"
            "- 'edit: <your rewritten version>'\n"
            "- 'cancel'"
        )

    def _render_current_candidate(self) -> str:
        if not self.pending_candidates:
            return "No pending draft. Ask for a new post first."

        current = self.pending_candidates[self.current_index]
        lines = ["Draft:"]
        lines.append(f"Mode: {current.mode.upper()}")
        if current.item:
            lines.append(f"Source: {current.item.source}")
            lines.append(f"Title: {current.item.title}")
            lines.append(f"Link: {current.item.link}")
        lines.append(f"Draft: {current.draft}")
        lines.append("")
        lines.append("Reply with:")
        lines.append("- approve")
        if len(self.pending_candidates) > 1:
            lines.append("- another")
        lines.append("- make it shorter")
        lines.append("- make it more critical")
        lines.append("- give it more opinion")
        lines.append("- edit: <your rewritten version>")
        lines.append("- cancel")
        return "\n".join(lines)

    def _current_candidate(self) -> DraftCandidate | None:
        if not self.pending_candidates:
            return None
        return self.pending_candidates[self.current_index]

    def _apply_manual_edit(self, text: str) -> str | None:
        stripped = text.strip()
        if not stripped.lower().startswith("edit:"):
            return None
        return stripped.split(":", 1)[1].strip() or None

    def _move_to_next_candidate(self) -> str:
        if not self.pending_candidates:
            return "No pending draft. Ask for a new post first."

        if len(self.pending_candidates) == 1:
            return "There isn't another saved option for this request. Ask for a new direction or say something like 'make it more opinionated'."

        self.current_index = (self.current_index + 1) % len(self.pending_candidates)
        return self._render_current_candidate()

    def _save_posted_item(self, candidate: DraftCandidate) -> None:
        if candidate.item:
            self.state.posted_urls.add(candidate.item.link.strip().lower())
            save_state(self.settings.state_file, self.state)

    def _strip_hashtags(self, text: str) -> str:
        cleaned = re.sub(r"(?<!\w)#[A-Za-z][A-Za-z0-9_]*", "", text)
        cleaned = re.sub(r"[ \t]+", " ", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    def _select_hashtags(self, candidate: DraftCandidate, text: str) -> list[str]:
        haystack = f"{text}\n{candidate.context}".lower()
        tags: list[str] = list(DEFAULT_HASHTAGS)

        for needle, hashtag in BRAND_HASHTAGS:
            if needle in haystack and hashtag not in tags:
                tags.append(hashtag)
                break

        for needle, hashtag in CONTEXT_HASHTAGS:
            if needle in haystack and hashtag not in tags:
                tags.append(hashtag)
                break

        deduped: list[str] = []
        for tag in tags:
            if tag not in deduped:
                deduped.append(tag)

        return deduped[:4]

    def _normalize_candidate_draft(self, candidate: DraftCandidate, draft: str) -> str:
        normalized = draft.strip()
        link = candidate.item.link if candidate.item else None

        if link and link in normalized:
            body = normalized.replace(link, "").strip()
        else:
            body = normalized

        body = self._strip_hashtags(body)
        hashtags = self._select_hashtags(candidate, body)
        if hashtags:
            body = f"{body}\n\n{' '.join(hashtags)}".strip()

        if link:
            return f"{body}\n\n{link}".strip()
        return body.strip()

    def handle_candidate_action(self, user_text: str) -> str:
        candidate = self._current_candidate()
        if candidate is None:
            return "No pending draft. Ask for a new post first."

        manual_edit = self._apply_manual_edit(user_text)
        if manual_edit:
            candidate.draft = self._normalize_candidate_draft(candidate, manual_edit)
            return self._render_current_candidate()

        revision: RevisionIntent = self.llm.parse_revision_intent(user_text)

        if revision.action == "cancel":
            self.pending_candidates = []
            self.current_index = 0
            return "Cancelled pending draft."

        if revision.action == "approve":
            result = self.poster.post(candidate.draft)
            if result.posted:
                self._save_posted_item(candidate)
            self.pending_candidates = []
            self.current_index = 0
            return result.message

        if revision.action == "another":
            return self._move_to_next_candidate()

        if revision.action == "revise" and revision.instruction:
            revised = self.llm.revise_post(
                policy_text=self.policy_text,
                current_draft=candidate.draft,
                user_instruction=revision.instruction,
                context=candidate.context,
            )
            candidate.draft = self._normalize_candidate_draft(candidate, revised)
            return self._render_current_candidate()

        return "I couldn't parse that. Try 'approve', 'another', 'make it shorter', 'give it more opinion', 'edit: ...', or 'cancel'."
