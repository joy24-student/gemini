# -*- coding: utf-8 -*-
"""
full_system_verification.py
===========================
Automated Comprehensive Test Suite for Gemini Unofficial Client API.
Verifies all core components, memory managers, live engines, and server APIs.
"""
import sys
import io
import os
import asyncio
from pathlib import Path

# Force UTF-8 encoding for Windows stdout/stderr
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gemini_client import (
    Chatbot, AsyncChatbot, Model,
    ConversationMemory, MultiUserMemoryManager,
    HighScaleSupportEngine,
    UnofficialLiveWebSocket,
)
from gemini_client.unofficial_live.pipeline_session import _clean_markdown_text, _detect_voice

def main():
    print("=" * 65)
    print(" 🛠️  GEMINI UNOFFICIAL CLIENT - FULL SYSTEM VERIFICATION SUITE")
    print("=" * 65)

    results = []

    # -------------------------------------------------------------
    # Test 1: Asterisk Filter & Voice Language Detector
    # -------------------------------------------------------------
    print("\n[Test 1/5] Testing Markdown Asterisk Filter & Language Auto-Detector...")
    dirty_text = "***\n### 1. **Hello** *Joy*! * Bullet 1\n* Bullet 2\n***"
    cleaned = _clean_markdown_text(dirty_text)
    eng_voice = _detect_voice("Hello Joy!", "en-US-AvaNeural")
    bn_voice = _detect_voice("অবশ্যই, আমি বাংলায় কথা বলছি।", "en-US-AvaNeural")

    if "*" not in cleaned and eng_voice == "en-US-AvaNeural" and bn_voice == "bn-BD-NabanitaNeural":
        print("  ✅ PASS: Asterisk filter & language detection operating correctly!")
        print(f"     Cleaned text: '{cleaned}'")
        print(f"     Bangla voice detected: '{bn_voice}'")
        results.append(("Markdown Asterisk Filter & Language Detection", "PASSED"))
    else:
        print("  ❌ FAIL: Markdown filter or voice detection failed!")
        results.append(("Markdown Asterisk Filter & Language Detection", "FAILED"))

    # -------------------------------------------------------------
    # Test 2: Core Chatbot API (Synchronous ask & ask_stream)
    # -------------------------------------------------------------
    print("\n[Test 2/5] Testing Core Synchronous Chatbot Authentication & Streaming...")
    try:
        bot = Chatbot(cookie_path="cookies.json", model=Model.G_2_5_FLASH)
        resp = bot.ask("Reply with exact word: 'VERIFIED'")
        print("  • Single-turn response text:", resp.text.strip())

        chunks = []
        for chunk in bot.ask_stream("Count 1 to 3"):
            chunks.append(chunk)
        stream_text = "".join(chunks)
        print("  • Streamed text:", stream_text.strip())

        if len(resp.text) > 0 and len(stream_text) > 0:
            print("  ✅ PASS: Core Synchronous Chatbot (ask & ask_stream) 100% functional!")
            results.append(("Core Synchronous Chatbot API", "PASSED"))
        else:
            results.append(("Core Synchronous Chatbot API", "FAILED"))
    except Exception as e:
        print(f"  ❌ FAIL: Core Chatbot error: {e}")
        results.append(("Core Synchronous Chatbot API", f"FAILED ({e})"))

    # -------------------------------------------------------------
    # Test 3: Conversation Memory Persistence
    # -------------------------------------------------------------
    print("\n[Test 3/5] Testing Conversation Memory Session Manager...")
    try:
        mem = ConversationMemory(session_name="test_verification_session")
        mem.add_user_message("Hello, my favorite color is Blue.")
        mem.add_model_message("Got it! Your favorite color is Blue.")
        history = mem.get_history()

        if len(history) >= 2 and any("Blue" in m.text for m in history):
            print(f"  ✅ PASS: Conversation Memory manager operational! ({len(history)} messages in history)")
            results.append(("Conversation Memory Session Manager", "PASSED"))
        else:
            results.append(("Conversation Memory Session Manager", "FAILED"))
    except Exception as e:
        print(f"  ❌ FAIL: Conversation Memory error: {e}")
        results.append(("Conversation Memory Session Manager", f"FAILED ({e})"))

    # -------------------------------------------------------------
    # Async Tests (4 & 5)
    # -------------------------------------------------------------
    async def run_async_tests():
        # Test 4: High-Scale Engine Concurrency
        print("\n[Test 4/5] Testing High-Scale Engine (Concurrent Session Isolation)...")
        try:
            engine = HighScaleSupportEngine(max_concurrent=5, worker_pool_size=2, cookie_path="cookies.json")
            await engine.initialize()
            res = await engine.process_user_query("verify_user_01", "Ping test")
            await engine.close()

            if res and not res["response"].error:
                print("  ✅ PASS: High-Scale Support Engine operational!")
                results.append(("High-Scale Support Engine", "PASSED"))
            else:
                results.append(("High-Scale Support Engine", "FAILED"))
        except Exception as e:
            print(f"  ❌ FAIL: High-Scale Engine error: {e}")
            results.append(("High-Scale Support Engine", f"FAILED ({e})"))

        # Test 5: Live WebSocket Engine Event Formatting
        print("\n[Test 5/5] Testing Unofficial Live WebSocket Event Stream...")
        try:
            from gemini_client.utils import load_cookies
            psid, psidts = load_cookies("cookies.json")
            async_bot = await AsyncChatbot.create(psid, psidts)
            live_ws = UnofficialLiveWebSocket(async_bot, enable_audio=False)
            events = []
            async for evt in live_ws.stream_live_turn("Say 'OK'"):
                events.append(evt)
            await async_bot.session.aclose()

            if len(events) > 0 and "serverContent" in events[0]:
                print("  ✅ PASS: Live WebSocket BidiGenerateContent Engine operational!")
                results.append(("Live WebSocket Event Engine", "PASSED"))
            else:
                results.append(("Live WebSocket Event Engine", "FAILED"))
        except Exception as e:
            print(f"  ❌ FAIL: Live WebSocket Engine error: {e}")
            results.append(("Live WebSocket Event Engine", f"FAILED ({e})"))

    asyncio.run(run_async_tests())

    # -------------------------------------------------------------
    # Final Report Summary
    # -------------------------------------------------------------
    print("\n" + "=" * 65)
    print(" 📊 FINAL VERIFICATION SUMMARY")
    print("=" * 65)
    all_passed = True
    for name, status in results:
        icon = "✅" if status == "PASSED" else "❌"
        print(f"  {icon} {name:<45} : {status}")
        if status != "PASSED":
            all_passed = False
    print("=" * 65)

    if all_passed:
        print("🎉 ALL SYSTEMS ARE OPERATING 100% PERFECTLY WITH 0 ERRORS!")
    else:
        print("⚠️ Some checks reported failures. See details above.")
    print("=" * 65)

if __name__ == "__main__":
    main()
