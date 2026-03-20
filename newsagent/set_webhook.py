from __future__ import annotations

import httpx

from .settings import load_settings
from .telegram_bot import ensure_telegram_settings


def main() -> None:
    settings = load_settings()
    ensure_telegram_settings(settings)

    if not settings.app_base_url:
        raise ValueError("APP_BASE_URL is missing in .env")

    webhook_url = settings.app_base_url.rstrip("/") + "/telegram/webhook"
    params = {"url": webhook_url}
    if settings.telegram_webhook_secret:
        params["secret_token"] = settings.telegram_webhook_secret

    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/setWebhook",
            data=params,
        )
        response.raise_for_status()
        print(response.text)


if __name__ == "__main__":
    main()
