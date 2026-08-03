# -*- coding: utf-8 -*-
"""
examples/memory_chat_demo.py
=============================
User-Friendly Context Memory Feature Demo.

Demonstrates:
  1. Auto-Resume & Auto-Save Session: Remembers conversation history automatically across restarts.
  2. System Instructions: Custom instructions for the AI model that persist in memory.
  3. Turn Inspection: Inspect recorded user/model turns via `bot.memory.get_history()`.
  4. Context Formatting: Generate full contextual prompts via `bot.memory.get_context_prompt()`.

Usage:
  python examples/memory_chat_demo.py --auto-cookie --session my_coding_bot
"""
import argparse
import sys
import io
from pathlib import Path

# Force UTF-8 encoding for Windows stdout/stderr
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add project root directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gemini_client import Chatbot, Model, ConversationMemory


def main():
    parser = argparse.ArgumentParser(description="Gemini Context Memory Demo")
    parser.add_argument("--cookies", default="cookies.json", help="Path to cookies JSON file")
    parser.add_argument("--auto-cookie", action="store_true", help="Auto-extract cookies from browser")
    parser.add_argument("--session", default="my_assistant", help="Named memory session name")
    args = parser.parse_args()

    print(f"\n🧠 Initializing Chatbot with Named Memory Session: '{args.session}'...")

    # Chatbot with automatic context memory + system instruction
    bot = Chatbot(
        cookie_path=args.cookies,
        auto_cookie=args.auto_cookie,
        model=Model.G_2_5_FLASH,
        session_name=args.session,
        system_instruction="You are a friendly and knowledgeable AI programming assistant.",
    )

    print(f"✅ Active memory turns in session '{args.session}': {len(bot.memory.messages)}")

    # Display prior conversation turns if resumed
    if len(bot.memory.messages) > 0:
        print("\n📜 Resumed Previous Memory History:")
        for msg in bot.memory.messages:
            label = "🧑 You" if msg.role == "user" else "🤖 Gemini"
            print(f"  {label} ({msg.timestamp[:19]}): {msg.text[:70]}...")
        print("─" * 60)

    # Interactive Chat Loop
    print("\n💬 Type your message below (type 'history' to inspect memory, 'clear' to reset, 'exit' to quit):\n")

    while True:
        try:
            user_input = input("🧑 You: ").strip()
            if not user_input:
                continue

            if user_input.lower() in ("exit", "quit", "bye"):
                print("\n💾 Memory automatically saved. Bye!")
                break

            if user_input.lower() == "history":
                print("\n📜 Full Session Memory History:")
                for i, msg in enumerate(bot.memory.messages, 1):
                    role = "User" if msg.role == "user" else "Gemini"
                    print(f"  [{i}] {role}: {msg.text}")
                print(f"Total turns: {len(bot.memory.messages)}\n")
                continue

            if user_input.lower() == "clear":
                bot.memory.clear()
                print("🧹 Memory cleared!\n")
                continue

            # Ask Gemini (memory automatically records prompt & response)
            response = bot.ask(user_input)
            print(f"🤖 Gemini: {response.text}\n")

        except (KeyboardInterrupt, EOFError):
            print("\n💾 Memory auto-saved. Exiting.")
            break


if __name__ == "__main__":
    main()
