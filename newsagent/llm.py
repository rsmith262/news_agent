from __future__ import annotations

import json
import re
from dataclasses import dataclass

from openai import OpenAI


@dataclass
class Intent:
    kind: str
    topic: str | None = None
    retrieval_framing: str | None = None
    writing_angle: str | None = None
    feed_hint: str | None = None
    today_only: bool = False


@dataclass
class CandidateAction:
    action: str
    index: int | None = None
    edit_text: str | None = None


@dataclass
class RevisionIntent:
    action: str
    instruction: str | None = None


def _extract_json(text: str) -> dict:
    text = text.strip()
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}


class LLM:
    def __init__(self, api_key: str, model: str):
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def _complete(self, prompt: str, temperature: float = 0.2) -> str:
        resp = self.client.responses.create(
            model=self.model,
            input=prompt,
            temperature=temperature,
        )
        return (resp.output_text or "").strip()

    def parse_intent(self, user_text: str) -> Intent:
        lowered = user_text.lower()
        # Deterministic guard so "news story" requests never drift into analysis/explainer.
        force_news = "news story" in lowered or "news" in lowered or "post me a story" in lowered or "story about" in lowered

        today_only_hint = bool(re.search(r"\btoday\b", lowered))
        about_match = re.search(r"\babout\s+(.+?)(?:\s+\bfrom\b|\s+\btoday\b|$)", user_text, flags=re.IGNORECASE)
        from_match = re.search(r"\bfrom\s+(.+?)(?:\s+\babout\b|\s+\btoday\b|$)", user_text, flags=re.IGNORECASE)
        topic_hint = about_match.group(1).strip(" ?.,") if about_match else None
        feed_hint_hint = from_match.group(1).strip(" ?.,") if from_match else None
        retrieval_hint = None
        writing_hint = None

        if "but make it" in lowered:
            tail = lowered.split("but make it", 1)[1].strip(" .!?")
            if tail:
                writing_hint = tail

        if any(term in lowered for term in {"risk", "risks", "safety", "harm", "harms"}):
            retrieval_hint = "risk"
        elif any(term in lowered for term in {"positive", "positives", "benefit", "benefits"}):
            retrieval_hint = "positive"
        elif any(term in lowered for term in {"critical of", "skeptical of"}):
            retrieval_hint = "critical"

        if writing_hint is None:
            if "critical" in lowered or "skeptical" in lowered:
                writing_hint = "critical"
            elif "optimistic" in lowered or "positive" in lowered:
                writing_hint = "optimistic"
            elif "opinion" in lowered or "take" in lowered:
                writing_hint = "opinionated"

        prompt = (
            "Classify the user request into JSON only with fields: "
            "kind, topic, retrieval_framing, writing_angle, feed_hint, today_only.\n"
            "kind must be one of: news, analysis, explain, help, unknown.\n"
            "Rules:\n"
            "- news: asks for a news story/news post.\n"
            "- analysis: asks for opinion/take/analysis on AI topic.\n"
            "- explain: asks to explain a concept.\n"
            "- retrieval_framing is the type of story to retrieve, such as positive, critical, risk-focused.\n"
            "- writing_angle is the requested perspective for the written post.\n"
            "- today_only true only if the user asks for today/date-limited content.\n"
            "- feed_hint is source name if user specifies one (like BBC, Guardian, Wired).\n"
            "Return strict JSON and no prose.\n\n"
            f"User text: {user_text}"
        )

        data = _extract_json(self._complete(prompt, temperature=0.0))
        kind = str(data.get("kind", "unknown")).lower().strip()
        if kind not in {"news", "analysis", "explain", "help", "unknown"}:
            kind = "unknown"
        if force_news:
            kind = "news"

        topic = data.get("topic")
        retrieval_framing = data.get("retrieval_framing")
        writing_angle = data.get("writing_angle")
        feed_hint = data.get("feed_hint")
        today_only = bool(data.get("today_only", False))

        final_topic = (str(topic).strip() or None) if topic is not None else None
        final_retrieval_framing = (
            str(retrieval_framing).strip() or None if retrieval_framing is not None else None
        )
        final_writing_angle = (
            str(writing_angle).strip() or None if writing_angle is not None else None
        )
        final_feed_hint = (str(feed_hint).strip() or None) if feed_hint is not None else None
        if topic_hint:
            final_topic = topic_hint
        if retrieval_hint:
            final_retrieval_framing = retrieval_hint
        if writing_hint:
            final_writing_angle = writing_hint
        if feed_hint_hint:
            final_feed_hint = feed_hint_hint

        return Intent(
            kind=kind,
            topic=final_topic,
            retrieval_framing=final_retrieval_framing,
            writing_angle=final_writing_angle,
            feed_hint=final_feed_hint,
            today_only=today_only or today_only_hint,
        )

    def parse_candidate_action(self, user_text: str, max_index: int) -> CandidateAction:
        prompt = (
            "Interpret the instruction for candidate handling and return JSON only with: "
            "action, index, edit_text.\n"
            "action must be one of: approve, edit, cancel, none.\n"
            f"index must be an integer from 1 to {max_index} when relevant, else null.\n"
            "edit_text is the rewritten post text when action is edit, else null.\n"
            "Return strict JSON and no prose.\n\n"
            f"Instruction: {user_text}"
        )

        data = _extract_json(self._complete(prompt, temperature=0.0))
        action = str(data.get("action", "none")).lower().strip()
        if action not in {"approve", "edit", "cancel", "none"}:
            action = "none"

        raw_index = data.get("index")
        index: int | None
        if isinstance(raw_index, int) and 1 <= raw_index <= max_index:
            index = raw_index
        else:
            index = None

        edit_text = data.get("edit_text")
        if edit_text is not None:
            edit_text = str(edit_text).strip() or None

        return CandidateAction(action=action, index=index, edit_text=edit_text)

    def parse_revision_intent(self, user_text: str) -> RevisionIntent:
        lowered = user_text.strip().lower()
        if lowered in {"approve", "post", "send", "publish"}:
            return RevisionIntent(action="approve")
        if lowered in {"cancel", "stop", "never mind"}:
            return RevisionIntent(action="cancel")
        if lowered in {"another", "another one", "next", "different one", "show another"}:
            return RevisionIntent(action="another")

        prompt = (
            "Interpret the user's instruction for revising a single social post draft. "
            "Return JSON only with fields: action, instruction.\n"
            "action must be one of: revise, another, approve, cancel, none.\n"
            "Use revise when the user asks for changes such as shorter, more critical, more opinionated, punchier, less hype, etc.\n"
            "instruction should contain the concrete rewrite direction when action=revise, else null.\n"
            "Return strict JSON and no prose.\n\n"
            f"Instruction: {user_text}"
        )
        data = _extract_json(self._complete(prompt, temperature=0.0))
        action = str(data.get("action", "none")).lower().strip()
        if action not in {"revise", "another", "approve", "cancel", "none"}:
            action = "none"
        instruction = data.get("instruction")
        if instruction is not None:
            instruction = str(instruction).strip() or None
        return RevisionIntent(action=action, instruction=instruction)

    def draft_news_post(
        self,
        policy_text: str,
        title: str,
        summary: str,
        source: str,
        topic: str | None,
        writing_angle: str | None,
    ) -> str:
        prompt = (
            "Write one Threads post draft using this policy and article details.\n"
            "Sound like a real person posting on Threads, not a press release or textbook.\n"
            "Use a clear angle. A light take is allowed if it stays grounded in the source.\n"
            "Keep it concise, specific, and readable.\n"
            "Avoid generic lead-ins like 'interesting to see' or bland recap language.\n"
            "Do not add claims not present in the article summary/title.\n"
            "Return only the blurb text (no URL).\n\n"
            f"Policy:\n{policy_text}\n\n"
            f"Topic preference: {topic or 'None'}\n"
            f"Writing angle: {writing_angle or 'None'}\n"
            f"Source: {source}\n"
            f"Title: {title}\n"
            f"Summary: {summary}\n"
        )
        return self._complete(prompt, temperature=0.7)

    def draft_analysis_post(self, policy_text: str, user_request: str) -> str:
        prompt = (
            "Write one Threads post draft for the user request.\n"
            "It should feel like a smart person posting a take, not a bland explainer.\n"
            "Allowed: subjective opinion. Prefer a clear point of view where relevant.\n"
            "Keep factual anchors where possible, but do not sound academic or corporate.\n"
            "No politics. Casual tone. Short enough for a social post.\n"
            "Return only the post text.\n\n"
            f"Policy:\n{policy_text}\n\n"
            f"User request: {user_request}"
        )
        return self._complete(prompt, temperature=0.9)

    def draft_explainer_post(self, policy_text: str, user_request: str) -> str:
        prompt = (
            "Write one Threads post explaining the concept in the user request.\n"
            "Make it feel human and social-first, not like training material.\n"
            "Use plain language, but include a useful angle, why it matters, or a light take where relevant.\n"
            "No politics. Keep it concise. Return only the post text.\n\n"
            f"Policy:\n{policy_text}\n\n"
            f"User request: {user_request}"
        )
        return self._complete(prompt, temperature=0.8)

    def revise_post(
        self,
        policy_text: str,
        current_draft: str,
        user_instruction: str,
        context: str | None = None,
    ) -> str:
        prompt = (
            "Revise this Threads post draft based on the user's instruction.\n"
            "Keep the voice human, concise, and social-native.\n"
            "Preserve any factual grounding and avoid adding unsupported claims.\n"
            "If the user asks for more opinion, you may make the stance clearer while staying credible.\n"
            "Return only the revised post text.\n\n"
            f"Policy:\n{policy_text}\n\n"
            f"Optional context:\n{context or 'None'}\n\n"
            f"Current draft:\n{current_draft}\n\n"
            f"User instruction:\n{user_instruction}"
        )
        return self._complete(prompt, temperature=0.8)
