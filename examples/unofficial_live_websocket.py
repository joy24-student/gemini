# -*- coding: utf-8 -*-
"""
examples/unofficial_live_websocket.py
======================================
Instant Official-Protocol WebSocket Live Streaming & Bridge Server Demo.

Demonstrates:
  1. Direct WebSocket Event Stream: Translates Gemini Web UI deltas into official
     BidiGenerateContentServerContent JSON events instantly (<5ms).
  2. Local WebSocket Bridge Server (ws://127.0.0.1:9000):
     Acts as a 100% compatible proxy for official Gemini Live applications.
     Any official Gemini Live client app can connect to ws://127.0.0.1:9000 with 0 API keys!

Usage:
  python examples/unofficial_live_websocket.py --auto-cookie --mode client
  or
  python examples/unofficial_live_websocket.py --auto-cookie --mode server
"""
import argparse
import asyncio
import json
import sys
import io
from pathlib import Path

# Force UTF-8 encoding for Windows stdout/stderr
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add project root directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gemini_client import (
    AsyncChatbot,
    CookieExtractor,
    load_cookies,
    UnofficialLiveWebSocket,
    UnofficialLiveBridgeServer,
)


async def client_demo(cookie_path: str, auto_cookie: bool):
    """Client demo: streams official BidiGenerateContentServerContent JSON events."""
    print("\n--- Instant Official-Protocol WebSocket Client Demo ---")

    if auto_cookie:
        extractor = CookieExtractor()
        cookies = extractor.extract_cookies(save_to_disk=False)
        psid, psidts = cookies['__Secure-1PSID'], cookies['__Secure-1PSIDTS']
    else:
        psid, psidts = load_cookies(cookie_path)

    bot = await AsyncChatbot.create(secure_1psid=psid, secure_1psidts=psidts)
    live_ws = UnofficialLiveWebSocket(bot, enable_audio=True)

    prompt = "Tell me a 2-sentence joke about programming."
    print(f"\n🧑 You: {prompt}\n")

    print("🤖 Gemini (Instant Official BidiGenerateContent ServerContent Events):")
    async for event in live_ws.stream_live_turn(prompt):
        # Pretty-print official JSON payload structure
        server_content = event.get("serverContent", {})
        turn = server_content.get("modelTurn", {})
        parts = turn.get("parts", [])

        for part in parts:
            if "text" in part:
                print(f"[TEXT] {part['text']}", flush=True)
            elif "inlineData" in part:
                mime = part["inlineData"]["mimeType"]
                b64_len = len(part["inlineData"]["data"])
                print(f"[AUDIO] {mime} (base64 length: {b64_len})", flush=True)

        if server_content.get("turnComplete"):
            print("✅ [turnComplete: true]")


async def server_demo(cookie_path: str, auto_cookie: bool, port: int):
    """Server demo: runs a local WebSocket Bridge Server on ws://127.0.0.1:port."""
    server = UnofficialLiveBridgeServer(
        host="127.0.0.1",
        port=port,
        cookie_path=cookie_path,
        auto_cookie=auto_cookie,
    )
    await server.start()

    print(f"\n🚀 Server running at ws://127.0.0.1:{port}")
    print("💡 Connect any application using official Gemini Live BidiGenerateContent protocol!")
    print("⏹️  Press Ctrl+C to stop.\n")

    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await server.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Unofficial Gemini Live WebSocket Demo")
    parser.add_argument("--cookies", default="cookies.json", help="Path to cookies JSON file")
    parser.add_argument("--auto-cookie", action="store_true", help="Auto-extract cookies from browser")
    parser.add_argument("--mode", choices=["client", "server"], default="client", help="Demo mode")
    parser.add_argument("--port", type=int, default=9000, help="Port for WebSocket Bridge Server")
    args = parser.parse_args()

    if args.mode == "server":
        asyncio.run(server_demo(args.cookies, args.auto_cookie, args.port))
    else:
        asyncio.run(client_demo(args.cookies, args.auto_cookie))
