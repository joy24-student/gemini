import asyncio
from gemini_client.core import AsyncChatbot
from gemini_client.cookie_manager import CookieExtractor
from rich import print

async def test():
    extractor = CookieExtractor()
    cookies = extractor.extract_cookies(save_to_disk=False)
    psid = cookies.get('__Secure-1PSID')
    psidts = cookies.get('__Secure-1PSIDTS')
    
    bot1 = await AsyncChatbot.create(secure_1psid=psid, secure_1psidts=psidts)
    bot2 = await AsyncChatbot.create(secure_1psid=psid, secure_1psidts=psidts)
    
    print("Request 1 on Bot 1:")
    async for chunk in bot1.ask_stream("Hello"):
        pass
    print("Bot 1 IDs:", bot1.conversation_id, bot1.response_id, bot1.choice_id)
    
    print("\nRequest 2 on Bot 2 (Transferring IDs):")
    bot2.conversation_id = bot1.conversation_id
    bot2.response_id = bot1.response_id
    bot2.choice_id = bot1.choice_id
    
    text2 = ""
    async for chunk in bot2.ask_stream("How are you?"):
        text2 += chunk
        print(chunk, end="")
    print("\nBot 2 response length:", len(text2))

if __name__ == "__main__":
    asyncio.run(test())
