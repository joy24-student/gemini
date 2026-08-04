import asyncio
import os
import httpx
import json
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
    print("Asking Gemini to generate an image...")
    bot = await AsyncChatbot.create(secure_1psid=env_psid, secure_1psidts=env_psidts or "")
    
    res = await bot.ask("Please generate an image of a red cat banner")
    print("\n--- Response Text ---")
    print(res.text)
    print("\n--- Parsed Images ---")
    print("images:", res.images)
    print("generated_images:", getattr(res, "generated_images", []))

    all_imgs = res.images + getattr(res, "generated_images", [])
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://gemini.google.com/",
    }
    cookies = {"__Secure-1PSID": env_psid}
    if env_psidts: cookies["__Secure-1PSIDTS"] = env_psidts

    async with httpx.AsyncClient(headers=headers, cookies=cookies, follow_redirects=True) as client:
        for img in all_imgs:
            u = img.get("url")
            print("\nTesting fetch for URL:", u)
            try:
                r = await client.get(u)
                print("Fetch Status Code:", r.status_code)
                print("Content-Type:", r.headers.get("content-type"))
                print("Content Length:", len(r.content))
            except Exception as e:
                print("Fetch Error:", e)

if __name__ == "__main__":
    asyncio.run(test())
