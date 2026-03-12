# NewsAgent (Local First)

Local CLI for testing a Telegram-style AI news posting workflow before wiring Telegram/Azure.

## What "Telegram-style" means locally
- You type natural language requests in a chat loop.
- Agent shows one draft first, with a couple of alternates available behind `another`.
- You can revise it in chat with natural instructions before approving.
- Default is dry-run (no live posting).

This mirrors the Telegram bot flow, so Telegram can later become just a transport layer.

## Run
1. Ensure `.env` contains `OPENAI_API_KEY` (and optional Threads vars).
2. Install dependencies:
   - `pip install -r requirements.txt`
3. Start local chat:
   - `python -m newsagent.cli`
4. Start Telegram bot in local polling mode:
   - `python -m newsagent.telegram_bot`

## Example requests
- `Can you post me a news story?`
- `Can you post me a news story from today?`
- `Can you post me a news story about robotics from BBC?`
- `Post me a story highlighting the risks of AI.`
- `Post me a story that highlights the positives of AI but make it critical.`
- `Write me a post analysing agentic AI tooling.`
- `Explain RAG in one post.`

Then reply with things like:
- `approve`
- `another`
- `make it shorter`
- `make it more critical`
- `give it more opinion`
- `edit: <your rewritten text>`
- `cancel`

## Config files
- `config/feeds.txt` approved RSS feeds
- `config/keywords.txt` default search keywords
- `config/posting_policy.md` tone/rules prompt template

## Telegram env vars
- `TELEGRAM_BOT_TOKEN` bot token from BotFather
- `TELEGRAM_CHAT_ID` your private Telegram chat ID
- `TELEGRAM_USER_ID` your Telegram user ID

## Notes
- Time/date filter uses UK timezone (`Europe/London`).
- Default news window is the last 2 days unless you explicitly ask for "today".
- Deduped posted links are stored in `.newsagent_state.json`.
- `DRY_RUN` defaults to true unless set to true/false in `.env`.
