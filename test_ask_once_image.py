import asyncio
from gemini_client import Chatbot

def test():
    bot = Chatbot(cookie_path="cookies.json")
    print("Testing bot.ask with text...")
    r = bot.ask("Describe a sunset over mountains in 2 sentences.")
    print("Response:", r.text[:150])
    assert len(r.text) > 0, "Text response failed"
    print("✅ Text ask working 100%!")

if __name__ == "__main__":
    test()
