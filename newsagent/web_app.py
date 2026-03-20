from __future__ import annotations

from fastapi import FastAPI, Header, HTTPException, Request
from telegram import Bot, Update

from .settings import load_settings
from .telegram_bot import build_runtime, ensure_telegram_settings


settings = load_settings()
ensure_telegram_settings(settings)
runtime = build_runtime(settings)
bot = Bot(token=settings.telegram_bot_token)
app = FastAPI(title="NewsAgent Webhook")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, bool]:
    if settings.telegram_webhook_secret:
        if x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
            raise HTTPException(status_code=401, detail="Invalid Telegram webhook secret")

    payload = await request.json()
    update = Update.de_json(payload, bot)
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    if message is None or user is None or chat is None:
        return {"ok": True}

    if not runtime.is_authorized(chat.id, user.id):
        await message.reply_text("Unauthorized chat.", disable_web_page_preview=True)
        return {"ok": True}

    text = message.text or ""
    result = runtime.handle_text(text)
    if result:
        await message.reply_text(result, disable_web_page_preview=True)

    return {"ok": True}
