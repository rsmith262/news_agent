from __future__ import annotations

from .agent import NewsAgent
from .settings import Settings, load_settings


def _ensure_telegram_settings(settings: Settings) -> None:
    if not settings.telegram_bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN is missing in .env")
    if settings.telegram_chat_id is None:
        raise ValueError("TELEGRAM_CHAT_ID is missing in .env")
    if settings.telegram_user_id is None:
        raise ValueError("TELEGRAM_USER_ID is missing in .env")


def run_telegram_bot() -> None:
    settings = load_settings()
    _ensure_telegram_settings(settings)

    try:
        from telegram import Update
        from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
    except ImportError as exc:
        raise ImportError(
            "python-telegram-bot is not installed. Run 'pip install -r requirements.txt'."
        ) from exc

    agent = NewsAgent(settings)

    def _is_authorized(update: Update) -> bool:
        message = update.effective_message
        user = update.effective_user
        chat = update.effective_chat
        if message is None or user is None or chat is None:
            return False
        return (
            chat.id == settings.telegram_chat_id
            and user.id == settings.telegram_user_id
        )

    async def _reject_unauthorized(update: Update) -> None:
        if update.effective_message is not None:
            await update.effective_message.reply_text("Unauthorized chat.")

    async def _handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        if not _is_authorized(update):
            await _reject_unauthorized(update)
            return

        message = update.effective_message
        if message is None or message.text is None:
            return

        user_text = message.text.strip()
        if not user_text:
            return

        if user_text.lower() == "help":
            result = agent.help_text()
        elif agent.pending_candidates:
            result = agent.handle_candidate_action(user_text)
            if result.startswith("No pending draft"):
                result = agent.handle_new_request(user_text)
        else:
            result = agent.handle_new_request(user_text)

        await message.reply_text(result)

    async def _start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        if not _is_authorized(update):
            await _reject_unauthorized(update)
            return
        if update.effective_message is not None:
            await update.effective_message.reply_text(
                "NewsAgent is running.\n\n" + agent.help_text()
            )

    async def _help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        if not _is_authorized(update):
            await _reject_unauthorized(update)
            return
        if update.effective_message is not None:
            await update.effective_message.reply_text(agent.help_text())

    app = Application.builder().token(settings.telegram_bot_token).build()
    app.add_handler(CommandHandler("start", _start))
    app.add_handler(CommandHandler("help", _help))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _handle_text))

    print("NewsAgent Telegram bot starting in polling mode.")
    print(
        f"Authorized chat={settings.telegram_chat_id} user={settings.telegram_user_id} "
        f"DRY_RUN={settings.dry_run}"
    )
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    run_telegram_bot()
