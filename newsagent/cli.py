from __future__ import annotations

from .agent import NewsAgent
from .settings import load_settings


def run_cli() -> None:
    settings = load_settings()
    agent = NewsAgent(settings)

    print("NewsAgent local chat (Telegram-style). Type 'help' or 'exit'.")
    print(f"DRY_RUN={settings.dry_run} | TZ={settings.timezone} | MODEL={settings.openai_model}")

    while True:
        try:
            user_text = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break

        if not user_text:
            continue

        if user_text.lower() in {"exit", "quit"}:
            print("Exiting.")
            break

        if user_text.lower() == "help":
            print(agent.help_text())
            continue

        if agent.pending_candidates:
            result = agent.handle_candidate_action(user_text)
            if result.startswith("I could not parse that") or result.startswith("No pending"):
                result = agent.handle_new_request(user_text)
            print(f"\nAgent: {result}")
            continue

        result = agent.handle_new_request(user_text)
        print(f"\nAgent: {result}")


if __name__ == "__main__":
    run_cli()
