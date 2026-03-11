from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class PostResult:
    posted: bool
    message: str


class ThreadsPoster:
    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run

    def post(self, text: str) -> PostResult:
        if self.dry_run:
            return PostResult(posted=False, message=f"DRY RUN: would post ->\n{text}")

        token = os.getenv("THREADS_TOKEN", "").strip()
        handle = os.getenv("THREADS_HANDLE", "").strip()
        if not token or not handle:
            return PostResult(posted=False, message="Missing THREADS_TOKEN or THREADS_HANDLE in .env")

        try:
            from threadspipepy.threadspipe import ThreadsPipe
        except Exception:
            return PostResult(
                posted=False,
                message="threadspipepy is not installed. Install it or run in DRY_RUN mode.",
            )

        try:
            api = ThreadsPipe(user_id=handle, access_token=token)
            response = api.post(text=text)
            return PostResult(posted=True, message=f"Posted to Threads. Response: {response}")
        except Exception as exc:
            return PostResult(posted=False, message=f"Posting failed: {exc}")
