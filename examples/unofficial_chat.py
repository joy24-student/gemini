# -*- coding: utf-8 -*-
"""
examples/unofficial_chat.py
===========================
100% Unofficial Gemini Web UI Chat Demo (Zero API Key Needed).

Demonstrates:
  - Multi-turn conversation with browser cookies
  - Automatic cookie extraction from installed browsers (Chrome, Edge, Firefox, Brave)
  - Synchronous & Asynchronous Chatbot interfaces
  - Accessing response metadata & generated image links

Usage:
  python examples/unofficial_chat.py --auto-cookie
  or
  python examples/unofficial_chat.py --cookies cookies.json
"""
import argparse
import asyncio
import sys
import io
from pathlib import Path

# Force UTF-8 encoding for Windows stdout/stderr
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add project root directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gemini_client import Chatbot, AsyncChatbot, Model, CookieExtractor


def sync_demo(cookie_path: str, auto_cookie: bool):
    print("\n--- Synchronous Unofficial Chatbot Demo ---")
    if auto_cookie:
        print("Extracting cookies automatically from installed browser...")
        bot = Chatbot(auto_cookie=True, model=Model.G_2_5_FLASH)
    else:
        bot = Chatbot(cookie_path=cookie_path, model=Model.G_2_5_FLASH)

    response = bot.ask("Hello! What model are you and what can you help me with?")
    print(f"\n🤖 Gemini: {response.text}\n")

    # Follow-up question in the same conversation
    response2 = bot.ask("Give me 3 tips for writing efficient Python code.")
    print(f"🤖 Gemini (turn 2): {response2.text}\n")


async def async_demo(cookie_path: str, auto_cookie: bool):
    print("\n--- Asynchronous Unofficial Chatbot Demo ---")
    if auto_cookie:
        extractor = CookieExtractor()
        cookies = extractor.extract_cookies(save_to_disk=False)
        psid, psidts = cookies['__Secure-1PSID'], cookies['__Secure-1PSIDTS']
    else:
        from gemini_client import load_cookies
        psid, psidts = load_cookies(cookie_path)

    bot = await AsyncChatbot.create(
        secure_1psid=psid,
        secure_1psidts=psidts,
        model=Model.G_2_5_FLASH,
    )

    try:
        response = await bot.ask("Write a short 3-line poem about space exploration.")
        print(f"\n🤖 Gemini (Async): {response.text}\n")
        print(f"Tokens used (approx): {response.usage_metadata.total_token_count}")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Unofficial Gemini Cookie Chat")
    parser.add_argument("--cookies", default="cookies.json", help="Path to cookies JSON file")
    parser.add_argument("--auto-cookie", action="store_true", help="Auto-extract cookies from browser")
    parser.add_argument("--async-mode", action="store_true", help="Run async demo")
    args = parser.parse_args()

    if args.async_mode:
        asyncio.run(async_demo(args.cookies, args.auto_cookie))
    else:
        sync_demo(args.cookies, args.auto_cookie)
