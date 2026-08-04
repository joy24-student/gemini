import asyncio
from gemini_client.core import AsyncChatbot
from gemini_client.cookie_manager import CookieExtractor
from rich import print

async def test():
    extractor = CookieExtractor()
    cookies = extractor.extract_cookies(save_to_disk=False)
    psid = cookies.get('__Secure-1PSID')
    psidts = cookies.get('__Secure-1PSIDTS')
    
    bot = await AsyncChatbot.create(secure_1psid=psid, secure_1psidts=psidts)
    print("First request:")
    async for chunk in bot.ask_stream("Hello"):
        print(chunk, end="")
    print("\n\nconv_id:", bot.conversation_id, "resp_id:", bot.response_id, "choice_id:", bot.choice_id)
    
    print("\nSecond request:")
    text2 = ""
    async for chunk in bot.ask_stream("How are you?"):
        text2 += chunk
        print(chunk, end="")
    print("\nSecond response length:", len(text2))
    
if __name__ == "__main__":
    asyncio.run(test())
