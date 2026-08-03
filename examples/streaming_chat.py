# -*- coding: utf-8 -*-
"""
examples/streaming_chat.py
============================
Phase 2 — Streaming text demo using the cookie-based Gemini API.

Unlike ask() which waits for the full response, ask_stream() yields
text chunks as soon as they arrive, giving a typewriter effect.

Usage:
  python examples/streaming_chat.py --cookies path/to/cookies.json

Or with auto cookie extraction from your browser:
  python examples/streaming_chat.py --auto-cookie
"""
import asyncio
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

from gemini_client import AsyncChatbot, Chatbot, Model


# ────────────────────────────────────────────────────────────────
# Async streaming example
# ────────────────────────────────────────────────────────────────
async def async_stream_demo(cookie_path: str):
    """Async streaming with AsyncChatbot.ask_stream()."""
    from gemini_client.utils import load_cookies

    psid, psidts = load_cookies(cookie_path)
    bot = await AsyncChatbot.create(
        secure_1psid=psid,
        secure_1psidts=psidts,
        model=Model.G_2_5_FLASH,  # Fast model, great for streaming demos
    )

    print("\n✅ Async Chatbot connected. Streaming mode ON.\n")

    prompts = [
        "Write a 5-line poem about artificial intelligence.",
        "Explain quantum entanglement in simple terms.",
    ]

    try:
        for prompt in prompts:
            print(f"\n{'─'*50}")
            print(f"🧑 You: {prompt}")
            print(f"🤖 Gemini (streaming): ", end="", flush=True)

            async for chunk in bot.ask_stream(prompt):
                print(chunk, end="", flush=True)

            print()  # newline after stream completes
    finally:
        await bot.session.close()


# ────────────────────────────────────────────────────────────────
# Sync streaming example
# ────────────────────────────────────────────────────────────────
def sync_stream_demo(cookie_path: str):
    """Sync streaming with Chatbot.ask_stream() generator."""
    bot = Chatbot(
        cookie_path=cookie_path,
        model=Model.G_2_5_FLASH,
    )

    print("\n✅ Sync Chatbot connected. Streaming mode ON.\n")

    prompt = "List 5 interesting facts about the ocean."

    print(f"🧑 You: {prompt}")
    print(f"🤖 Gemini (streaming): ", end="", flush=True)

    for chunk in bot.ask_stream(prompt):
        print(chunk, end="", flush=True)

    print("\n")


# ────────────────────────────────────────────────────────────────
# Interactive streaming REPL
# ────────────────────────────────────────────────────────────────
async def interactive_stream(cookie_path: str, auto_cookie: bool):
    """Interactive chat loop with streaming output."""
    from gemini_client.utils import load_cookies

    if auto_cookie:
        bot = Chatbot(auto_cookie=True, model=Model.G_2_5_FLASH)
    else:
        bot = Chatbot(cookie_path=cookie_path, model=Model.G_2_5_FLASH)

    print("\n✅ Streaming chat ready! Type messages (type 'exit' to quit).\n")

    loop = asyncio.get_event_loop()

    while True:
        try:
            message = await loop.run_in_executor(None, input, "🧑 You: ")
            if message.strip().lower() in ("exit", "quit", "bye"):
                break
            if not message.strip():
                continue

            print("🤖 Gemini: ", end="", flush=True)
            for chunk in bot.ask_stream(message):
                print(chunk, end="", flush=True)
            print()

        except (KeyboardInterrupt, EOFError):
            break

    print("\n✅ Chat ended.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gemini Streaming Text Demo")
    parser.add_argument("--cookies", default="cookies.json", help="Path to cookies JSON")
    parser.add_argument("--auto-cookie", action="store_true",
                        help="Auto-extract cookies from browser")
    parser.add_argument("--mode", choices=["async", "sync", "interactive"],
                        default="interactive", help="Demo mode")
    args = parser.parse_args()

    if args.mode == "async":
        asyncio.run(async_stream_demo(args.cookies))
    elif args.mode == "sync":
        sync_stream_demo(args.cookies)
    else:
        asyncio.run(interactive_stream(args.cookies, args.auto_cookie))
