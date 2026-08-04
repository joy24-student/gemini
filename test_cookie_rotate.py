import asyncio
import os
from gemini_client.core import AsyncChatbot

env_psid = None
env_psidts = None
if os.path.exists('.env'):
    with open('.env', 'r', encoding='utf-8') as f:
        for line in f:
            if line.startswith('GEMINI_1PSID='):
                env_psid = line.strip().split('GEMINI_1PSID=', 1)[1]
            elif line.startswith('GEMINI_1PSIDTS='):
                env_psidts = line.strip().split('GEMINI_1PSIDTS=', 1)[1]

async def test():
    print("Testing automatic cookie rotation with Google...")
    bot = await AsyncChatbot.create(secure_1psid=env_psid, secure_1psidts=env_psidts or "")
    print("Initial PSIDTS:", bot.secure_1psidts[:30] + "..." if bot.secure_1psidts else "None")
    
    try:
        new_ts = await bot._AsyncChatbot__rotate_cookies()
        print("Rotated fresh PSIDTS from Google:", new_ts[:30] + "..." if new_ts else "None")
        print("✅ Cookie Rotation Succeeded!")
    except Exception as e:
        print("Rotation Error:", e)

if __name__ == "__main__":
    asyncio.run(test())
