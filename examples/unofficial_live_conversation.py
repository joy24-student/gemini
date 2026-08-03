# -*- coding: utf-8 -*-
"""
examples/unofficial_live_conversation.py
=========================================
Advanced Unofficial Real-Time Live Conversation Demo (Zero API Key Needed).

Supports 2 high-speed interaction modes:
  1. Pipeline Mode: Direct HTTP/2 StreamGenerate with sentence-pipelined TTS audio (<200ms latency).
  2. Playwright Mode: Headless Chromium process engine with automated browser context & DOM stream interception.

Usage:
  python examples/unofficial_live_conversation.py --auto-cookie --mode pipeline
  or
  python examples/unofficial_live_conversation.py --auto-cookie --mode playwright
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

from gemini_client import UnofficialLiveChatbot, CookieExtractor
from gemini_client.unofficial_live import PlaywrightLiveSession


async def run_pipeline_mode(cookie_path: str, auto_cookie: bool):
    """Pipeline mode: direct HTTP/2 streaming + sentence-level TTS synthesis."""
    print("\n--- Unofficial Real-Time Voice Pipeline Mode ---")
    async with UnofficialLiveChatbot(cookie_path=cookie_path, auto_cookie=auto_cookie) as bot:
        await bot.start_voice_pipeline()


async def run_playwright_mode(cookie_path: str, auto_cookie: bool):
    """Playwright mode: headless Chromium browser context + network/DOM stream interception."""
    print("\n--- Playwright Chromium Real-Time Process Engine Mode ---")

    if auto_cookie:
        extractor = CookieExtractor()
        cookies = extractor.extract_cookies(save_to_disk=False)
        psid, psidts = cookies['__Secure-1PSID'], cookies['__Secure-1PSIDTS']
    else:
        from gemini_client import load_cookies
        psid, psidts = load_cookies(cookie_path)

    session = PlaywrightLiveSession(secure_1psid=psid, secure_1psidts=psidts, headless=True)
    try:
        await session.start()

        # Send interactive messages through the Playwright browser process
        print("\nReady! Enter your prompt below (type 'exit' to quit):\n")
        loop = asyncio.get_event_loop()
        while True:
            try:
                prompt = await loop.run_in_executor(None, input, "🧑 You: ")
                if prompt.strip().lower() in ("exit", "quit", "bye"):
                    break
                if not prompt.strip():
                    continue
                await session.send_message(prompt)
            except (KeyboardInterrupt, EOFError):
                break
    finally:
        await session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Unofficial Real-Time Live Conversation Demo")
    parser.add_argument("--cookies", default="cookies.json", help="Path to cookies JSON file")
    parser.add_argument("--auto-cookie", action="store_true", help="Auto-extract cookies from browser")
    parser.add_argument("--mode", choices=["pipeline", "playwright"], default="pipeline",
                        help="Live engine mode: 'pipeline' (HTTP/2 + TTS) or 'playwright' (Headless Chromium)")
    args = parser.parse_args()

    if args.mode == "playwright":
        asyncio.run(run_playwright_mode(args.cookies, args.auto_cookie))
    else:
        asyncio.run(run_pipeline_mode(args.cookies, args.auto_cookie))
