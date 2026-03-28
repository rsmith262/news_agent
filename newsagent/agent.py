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
    topic_tag: str | None = None


THREADS_MAX_POST_LENGTH = 500
DEFAULT_TOPIC_TAG = "Artificial Intelligence"
BRAND_TOPIC_TAGS: tuple[tuple[str, str], ...] = (
    ("openai", "OpenAI"),
    ("chatgpt", "ChatGPT"),
    ("anthropic", "Anthropic"),
    ("claude", "Claude"),
    ("gemini", "Gemini"),
    ("mistral", "Mistral"),
    ("llama", "Llama"),
    ("deepseek", "DeepSeek"),
)
CONTEXT_TOPIC_TAGS: tuple[tuple[str, str], ...] = (
    ("machine learning", "Machine Learning"),
    ("llm", "LLM"),
    ("agent", "AI Agents"),
    ("agents", "AI Agents"),
    ("robot", "Robotics"),
    ("robots", "Robotics"),
    ("generative", "Generative AI"),
    ("genai", "Generative AI"),
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

    def _build_news_candidates(self, intent: Intent) -> tuple[list[DraftCandidate], str]:
        matched_items = fetch_ranked_news(
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
        if not matched_items:
            return [], "no_matches"

        items = self._filter_deduped(matched_items)
        if not items:
            return [], "deduped_only"

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
            candidate = DraftCandidate(
                item=item,
                draft=draft,
                mode="news",
                context=context,
                topic_tag=self._select_topic_tag(context),
            )
            candidate.draft = self._normalize_candidate_draft(candidate, candidate.draft)
            candidates.append(candidate)

        return candidates, "ok"

    def _build_analysis_candidates(self, user_text: str) -> list[DraftCandidate]:
        draft = self.llm.draft_analysis_post(self.policy_text, user_text)
        candidate = DraftCandidate(
            item=None,
            draft=draft,
            mode="analysis",
            context=f"Mode: analysis\nOriginal request: {user_text}",
            topic_tag=self._select_topic_tag(user_text, draft),
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
            topic_tag=self._select_topic_tag(user_text, draft),
        )
        candidate.draft = self._normalize_candidate_draft(candidate, candidate.draft)
        return [candidate]

    def debug_topic(self, topic: str) -> str:
        request = SearchRequest(
            topic=topic.strip() or None,
            retrieval_framing=None,
            feed_hint=None,
            today_only=False,
        )
        matched_items = fetch_ranked_news(
            feed_urls=self.feed_urls,
            request=request,
            default_keywords=self.default_keywords,
            timezone_name=self.settings.timezone,
        )
        deduped_items = self._filter_deduped(matched_items)

        lines = [f"Debug topic: {topic}"]
        lines.append(f"Matched before dedupe: {len(matched_items)}")
        lines.append(f"Matched after dedupe: {len(deduped_items)}")

        if matched_items:
            lines.append("")
            lines.append("Top raw matches:")
            for item in matched_items[:5]:
                lines.append(f"- {item.source} | {item.title}")

        if deduped_items:
            lines.append("")
            lines.append("Top deduped matches:")
            for item in deduped_items[:5]:
                lines.append(f"- {item.source} | {item.title}")

        if not matched_items:
            lines.append("")
            lines.append("No raw matches found in the current feed set.")

        return "\n".join(lines)

    def debug_intent(self, user_text: str) -> str:
        intent = self.llm.parse_intent(user_text)
        lines = ["Parsed intent:"]
        lines.append(f"kind: {intent.kind}")
        lines.append(f"topic: {intent.topic or 'None'}")
        lines.append(f"retrieval_framing: {intent.retrieval_framing or 'None'}")
        lines.append(f"writing_angle: {intent.writing_angle or 'None'}")
        lines.append(f"feed_hint: {intent.feed_hint or 'None'}")
        lines.append(f"today_only: {intent.today_only}")
        return "\n".join(lines)

    def handle_new_request(self, user_text: str) -> str:
        intent = self.llm.parse_intent(user_text)
        no_match_reason = "no_matches"

        if intent.kind == "news":
            candidates, no_match_reason = self._build_news_candidates(intent)
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
            if no_match_reason == "deduped_only":
                return (
                    "I found matching stories, but they were all already in the dedupe state. "
                    "Try another topic or clear the posted state if you want to reuse them."
                )
            return (
                "No matching stories found for that request in the current feed set and date window. "
                "Try another topic, a specific source, or say 'today' if you want a stricter same-day search."
            )

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
        if current.topic_tag:
            lines.append(f"Topic tag: {current.topic_tag}")
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

    def _select_topic_tag(self, *parts: str) -> str:
        haystack = "\n".join(parts).lower()
        for needle, topic_tag in BRAND_TOPIC_TAGS:
            if needle in haystack:
                return topic_tag
        for needle, topic_tag in CONTEXT_TOPIC_TAGS:
            if needle in haystack:
                return topic_tag
        return DEFAULT_TOPIC_TAG

    def _truncate_text(self, text: str, limit: int) -> str:
        normalized = re.sub(r"[ \t]+", " ", text.strip())
        if len(normalized) <= limit:
            return normalized
        if limit <= 3:
            return normalized[:limit]
        trimmed = normalized[: limit - 3].rstrip()
        last_space = trimmed.rfind(" ")
        if last_space >= max(20, limit // 2):
            trimmed = trimmed[:last_space].rstrip()
        return f"{trimmed}..."

    def _remove_em_dashes(self, text: str) -> str:
        return text.replace("—", ", ").replace("–", ", ")

    def _normalize_candidate_draft(self, candidate: DraftCandidate, draft: str) -> str:
        normalized = draft.strip()
        link = candidate.item.link if candidate.item else None

        if link and link in normalized:
            body = normalized.replace(link, "").strip()
        else:
            body = normalized

        body = self._strip_hashtags(body)
        body = self._remove_em_dashes(body)
        if link:
            available_body = THREADS_MAX_POST_LENGTH - len(link) - 2
            if available_body <= 0:
                return self._truncate_text(link, THREADS_MAX_POST_LENGTH)
            body = self._truncate_text(body, available_body)
            return f"{body}\n\n{link}".strip()
        return self._truncate_text(body, THREADS_MAX_POST_LENGTH).strip()

    def handle_candidate_action(self, user_text: str) -> str:
        candidate = self._current_candidate()
        if candidate is None:
            return "No pending draft. Ask for a new post first."

        manual_edit = self._apply_manual_edit(user_text)
        if manual_edit:
            candidate.draft = self._normalize_candidate_draft(candidate, manual_edit)
            candidate.topic_tag = (
                self._select_topic_tag(candidate.context)
                if candidate.item
                else self._select_topic_tag(candidate.context, candidate.draft)
            )
            return self._render_current_candidate()

        revision: RevisionIntent = self.llm.parse_revision_intent(user_text)

        if revision.action == "cancel":
            self.pending_candidates = []
            self.current_index = 0
            return "Cancelled pending draft."

        if revision.action == "approve":
            result = self.poster.post(candidate.draft, topic_tag=candidate.topic_tag)
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
            candidate.topic_tag = (
                self._select_topic_tag(candidate.context)
                if candidate.item
                else self._select_topic_tag(candidate.context, candidate.draft)
            )
            return self._render_current_candidate()

        return "I couldn't parse that. Try 'approve', 'another', 'make it shorter', 'give it more opinion', 'edit: ...', or 'cancel'."
