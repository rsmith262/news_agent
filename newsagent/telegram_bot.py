from __future__ import annotations

from dataclasses import dataclass

from .agent import NewsAgent
from .settings import Settings, load_settings


def ensure_telegram_settings(settings: Settings) -> None:
    if not settings.telegram_bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN is missing in .env")
    if settings.telegram_chat_id is None:
        raise ValueError("TELEGRAM_CHAT_ID is missing in .env")
    if settings.telegram_user_id is None:
        raise ValueError("TELEGRAM_USER_ID is missing in .env")


@dataclass
class TelegramRuntime:
    settings: Settings
    agent: NewsAgent

    def status_text(self) -> str:
        return (
            f"NewsAgent is running.\n"
            f"Version: {self.settings.app_version}\n"
            f"DRY_RUN: {self.settings.dry_run}\n\n"
            f"{self.agent.help_text()}"
        )

    def is_authorized(self, chat_id: int | None, user_id: int | None) -> bool:
        return (
            chat_id == self.settings.telegram_chat_id
            and user_id == self.settings.telegram_user_id
        )

    def handle_text(self, user_text: str) -> str:
        cleaned = user_text.strip()
        if not cleaned:
            return ""
        if cleaned.lower() in {"/start", "start"}:
            return self.status_text()
        if cleaned.lower() in {"/help", "help"}:
            return self.status_text()
        if cleaned.lower().startswith("/debug "):
            topic = cleaned.split(" ", 1)[1].strip()
            if not topic:
                return "Usage: /debug <topic>"
            return self.agent.debug_topic(topic)
        if cleaned.lower().startswith("/intent "):
            request_text = cleaned.split(" ", 1)[1].strip()
            if not request_text:
                return "Usage: /intent <full request>"
            return self.agent.debug_intent(request_text)
        if self.agent.pending_candidates:
            result = self.agent.handle_candidate_action(cleaned)
            if result.startswith("No pending draft"):
                result = self.agent.handle_new_request(cleaned)
            return result
        return self.agent.handle_new_request(cleaned)


def build_runtime(settings: Settings | None = None) -> TelegramRuntime:
    resolved = settings or load_settings()
    ensure_telegram_settings(resolved)
    return TelegramRuntime(settings=resolved, agent=NewsAgent(resolved))


def run_telegram_bot() -> None:
    runtime = build_runtime()

    try:
        from telegram import Update
        from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
    except ImportError as exc:
        raise ImportError(
            "python-telegram-bot is not installed. Run 'pip install -r requirements.txt'."
        ) from exc

    async def _reject_unauthorized(update: Update) -> None:
        if update.effective_message is not None:
            await update.effective_message.reply_text(
                "Unauthorized chat.",
                disable_web_page_preview=True,
            )

    async def _handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        message = update.effective_message
        user = update.effective_user
        chat = update.effective_chat
        if message is None or user is None or chat is None:
            return
        if not runtime.is_authorized(chat.id, user.id):
            await _reject_unauthorized(update)
            return

        result = runtime.handle_text(message.text or "")
        if result:
            await message.reply_text(result, disable_web_page_preview=True)

    async def _start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        user = update.effective_user
        chat = update.effective_chat
        if user is None or chat is None:
            return
        if not runtime.is_authorized(chat.id, user.id):
            await _reject_unauthorized(update)
            return
        if update.effective_message is not None:
            await update.effective_message.reply_text(
                runtime.status_text(),
                disable_web_page_preview=True,
            )

    async def _help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        user = update.effective_user
        chat = update.effective_chat
        if user is None or chat is None:
            return
        if not runtime.is_authorized(chat.id, user.id):
            await _reject_unauthorized(update)
            return
        if update.effective_message is not None:
            await update.effective_message.reply_text(
                runtime.status_text(),
                disable_web_page_preview=True,
            )

    app = Application.builder().token(runtime.settings.telegram_bot_token).build()
    app.add_handler(CommandHandler("start", _start))
    app.add_handler(CommandHandler("help", _help))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _handle_text))

    print("NewsAgent Telegram bot starting in polling mode.")
    print(
        f"Authorized chat={runtime.settings.telegram_chat_id} "
        f"user={runtime.settings.telegram_user_id} DRY_RUN={runtime.settings.dry_run}"
    )
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    run_telegram_bot()
