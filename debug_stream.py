import asyncio
import traceback
from gemini_client.core import AsyncChatbot
from gemini_client.utils import load_cookies

async def main():
    try:
        psid, psidts = load_cookies("cookies.json")
        bot = await AsyncChatbot.create(psid, psidts)
        print("Bot initialized successfully. SNlM0e:", bot.SNlM0e[:20])
        print("Starting ask_stream...")
        async for chunk in bot.ask_stream("Hello, count 1 to 3"):
            print("Chunk:", repr(chunk))
        await bot.session.aclose()
    except Exception as e:
        print("Exception in main:", type(e), repr(e))
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
