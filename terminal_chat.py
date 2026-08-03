# -*- coding: utf-8 -*-
"""
terminal_chat.py
================
Interactive Terminal CLI Chat for Google Gemini.

Usage:
  python terminal_chat.py
  python terminal_chat.py --auto-cookie
  python terminal_chat.py --cookies custom_cookies.json
"""
import sys
import os
import io
import argparse
from pathlib import Path

# Force UTF-8 encoding for Windows stdout/stderr
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add project root directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from gemini_client import Chatbot, Model

def main():
    parser = argparse.ArgumentParser(description="Interactive Gemini Terminal Chat")
    parser.add_argument("--cookies", default="cookies.json", help="Path to cookies JSON file (default: cookies.json)")
    parser.add_argument("--auto-cookie", action="store_true", help="Auto-extract cookies from browser")
    args = parser.parse_args()

    print("=" * 65)
    print(" 🤖 GEMINI TERMINAL CHAT INTERFACE ")
    print("=" * 65)

    try:
        if args.auto_cookie:
            print("🔍 Extracting cookies automatically from installed browser...")
            bot = Chatbot(auto_cookie=True, model=Model.G_2_5_FLASH)
        else:
            cookie_path = args.cookies
            if not os.path.exists(cookie_path):
                print(f"❌ Error: Cookie file '{cookie_path}' not found.")
                print("Tip: Run with '--auto-cookie' or create 'cookies.json'.")
                return
            print(f"🔑 Loading cookies from '{cookie_path}'...")
            bot = Chatbot(cookie_path=cookie_path, model=Model.G_2_5_FLASH)

        print("✅ Session initialized successfully!")
        print("\nType your message below and press Enter.")
        print("Commands: 'exit' / 'quit' to stop | 'clear' to start fresh conversation")
        print("-" * 65)

        while True:
            try:
                user_input = input("\n👤 You: ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\n\n👋 Exiting session. Goodbye!")
                break

            if not user_input:
                continue

            if user_input.lower() in ["exit", "quit", "q"]:
                print("\n👋 Exiting session. Goodbye!")
                break

            if user_input.lower() == "clear":
                bot.async_chatbot.conversation_id = ""
                bot.async_chatbot.response_id = ""
                bot.async_chatbot.choice_id = ""
                print("🧹 Conversation context cleared!")
                continue

            print("🤖 Gemini: ", end="", flush=True)
            try:
                for chunk in bot.ask_stream(user_input):
                    print(chunk, end="", flush=True)
                print()
            except Exception as err:
                print(f"\n❌ Error getting response: {err}")

    except Exception as err:
        print(f"\n❌ Failed to start chat session: {err}")

if __name__ == "__main__":
    main()
