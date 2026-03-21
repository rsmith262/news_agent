from __future__ import annotations

import os
from dataclasses import dataclass

import httpx


THREADS_API_BASE = "https://graph.threads.net"


@dataclass
class PostResult:
    posted: bool
    message: str


class ThreadsPoster:
    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run

    def _get_access_token(self) -> str:
        return os.getenv("THREADS_ACCESS_TOKEN", "").strip()

    def _create_text_container(
        self,
        client: httpx.Client,
        access_token: str,
        text: str,
        topic_tag: str | None = None,
    ) -> str:
        payload = {
            "media_type": "TEXT",
            "text": text,
            "access_token": access_token,
        }
        if topic_tag:
            payload["topic_tag"] = topic_tag
        response = client.post(
            f"{THREADS_API_BASE}/me/threads",
            data=payload,
        )
        response.raise_for_status()
        payload = response.json()
        creation_id = str(payload.get("id", "")).strip()
        if not creation_id:
            raise ValueError(f"Threads API did not return a container id: {payload}")
        return creation_id

    def _publish_container(self, client: httpx.Client, access_token: str, creation_id: str) -> dict:
        response = client.post(
            f"{THREADS_API_BASE}/me/threads_publish",
            data={
                "creation_id": creation_id,
                "access_token": access_token,
            },
        )
        response.raise_for_status()
        return response.json()

    def post(self, text: str, topic_tag: str | None = None) -> PostResult:
        if self.dry_run:
            topic_line = f"\n\nTopic tag: {topic_tag}" if topic_tag else ""
            return PostResult(posted=False, message=f"DRY RUN: would post ->\n{text}{topic_line}")

        access_token = self._get_access_token()
        if not access_token:
            return PostResult(posted=False, message="Missing THREADS_ACCESS_TOKEN in .env")

        try:
            with httpx.Client(timeout=30.0) as client:
                creation_id = self._create_text_container(client, access_token, text, topic_tag=topic_tag)
                publish_payload = self._publish_container(client, access_token, creation_id)
            post_id = str(publish_payload.get("id", "")).strip()
            if post_id:
                return PostResult(posted=True, message=f"Posted to Threads. Post id: {post_id}")
            return PostResult(posted=True, message=f"Posted to Threads. Response: {publish_payload}")
        except httpx.HTTPStatusError as exc:
            try:
                details = exc.response.text
            except Exception:
                details = str(exc)
            return PostResult(posted=False, message=f"Threads API error: {details}")
        except Exception as exc:
            return PostResult(posted=False, message=f"Posting failed: {exc}")
