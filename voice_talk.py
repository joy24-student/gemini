# -*- coding: utf-8 -*-
"""
voice_talk.py
=============
Interactive Hands-Free Voice Chat for Google Gemini.

Features:
  1. Speak into your Microphone 🎤 (Speech-to-Text).
  2. Gemini responds out loud through your Speakers 🔊 (Edge TTS Audio).
  3. Interactive fallback to keyboard input if mic is unavailable.

Usage:
  python voice_talk.py
  python voice_talk.py --auto-cookie
"""
import sys
import os
import io
import asyncio
import argparse
from pathlib import Path

# Force UTF-8 encoding for Windows stdout/stderr
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add project root directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from gemini_client import AsyncChatbot, CookieExtractor, load_cookies, Model
from gemini_client.unofficial_live import PipelineLiveSession

async def main():
    parser = argparse.ArgumentParser(description="Interactive Voice Chat with Gemini")
    parser.add_argument("--cookies", default="cookies.json", help="Path to cookies JSON file")
    parser.add_argument("--auto-cookie", action="store_true", help="Auto-extract cookies from browser")
    parser.add_argument("--voice", default="en-US-AvaNeural", help="TTS Voice (default: en-US-AvaNeural)")
    parser.add_argument("--mic", action="store_true", help="Enable hands-free microphone listening")
    args = parser.parse_args()

    print("=" * 65)
    print(" 🎙️  GEMINI REAL-TIME VOICE CHAT ")
    print("=" * 65)

    if args.auto_cookie:
        extractor = CookieExtractor()
        cookies = extractor.extract_cookies(save_to_disk=False)
        psid, psidts = cookies['__Secure-1PSID'], cookies['__Secure-1PSIDTS']
    else:
        if not os.path.exists(args.cookies):
            print(f"❌ Cookie file '{args.cookies}' not found!")
            return
        psid, psidts = load_cookies(args.cookies)

    print("🔑 Initializing session with Google Gemini...")
    bot = await AsyncChatbot.create(secure_1psid=psid, secure_1psidts=psidts, model=Model.G_2_5_FLASH)
    pipeline = PipelineLiveSession(bot, voice_name=args.voice)

    print("✅ Voice engine initialized!")
    print(f"🔊 Speaker Output: Enabled (Voice: {args.voice})")
    print("📝 Press Enter to talk or type your message. Type 'exit' to quit.")
    print("-" * 65)

    # Initialize SpeechRecognition if mic requested
    recognizer = None
    mic_device = None
    if args.mic:
        try:
            import speech_recognition as sr
            recognizer = sr.Recognizer()
            mic_device = sr.Microphone()
            print("🎤 Microphone listening: ENABLED")
        except Exception as e:
            print(f"⚠️ Microphone setup warning: {e}. Falling back to text input.")

    loop = asyncio.get_event_loop()
    while True:
        try:
            if recognizer and mic_device:
                print("\n🎙️ Listening... (Speak now or press Ctrl+C to switch to typing)")
                try:
                    with mic_device as source:
                        recognizer.adjust_for_ambient_noise(source, duration=0.5)
                        audio = recognizer.listen(source, timeout=5, phrase_time_limit=10)
                    user_text = recognizer.recognize_google(audio)
                    print(f"🧑 You (Voice): {user_text}")
                except Exception:
                    # Fallback to keyboard input
                    user_text = await loop.run_in_executor(None, input, "\n🧑 You: ")
            else:
                user_text = await loop.run_in_executor(None, input, "\n🧑 You: ")

            user_text = user_text.strip()
            if not user_text:
                continue

            if user_text.lower() in ("exit", "quit", "bye"):
                print("\n👋 Goodbye!")
                break

            await pipeline.send_voice_prompt(user_text)

        except (KeyboardInterrupt, EOFError):
            print("\n👋 Exiting session. Goodbye!")
            break

if __name__ == "__main__":
    asyncio.run(main())
