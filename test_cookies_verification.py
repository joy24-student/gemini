import sys
import io

# Force UTF-8 encoding for Windows stdout
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from gemini_client import Chatbot, Model

print("=" * 60)
print("GEMINI UNOFFICIAL CLIENT - FULL COOKIE & FUNCTIONALITY TEST")
print("=" * 60)

try:
    print("\n[Step 1] Initializing Chatbot with cookies.json...")
    bot = Chatbot(cookie_path="cookies.json", model=Model.G_2_5_FLASH)
    print("✅ Chatbot session initialized successfully!")
    print(f"   SNlM0e Token acquired: {bool(bot.async_chatbot.SNlM0e)}")

    print("\n[Step 2] Sending text query to Gemini Web UI...")
    response = bot.ask("Respond with: 'Authentication and Cookie verification successful!'")
    print("✅ Received Response from Gemini!")
    print("-" * 50)
    print(response.text)
    print("-" * 50)

    print("\n[Step 3] Testing Streaming Chat (ask_stream)...")
    print("Stream output: ", end="", flush=True)
    for chunk in bot.ask_stream("Give a short 1-sentence greeting."):
        print(chunk, end="", flush=True)
    print("\n\n✅ Streaming verified!")

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED: COOKIES ARE VALID AND FULLY WORKING!")
    print("=" * 60)

except Exception as e:
    print("\n❌ TEST FAILED!")
    print(f"Error Details: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
