import asyncio
import os
import httpx

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
    print("Testing PSIDTS extraction directly from https://gemini.google.com/app...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://gemini.google.com/",
    }
    cookies = {"__Secure-1PSID": env_psid}

    async with httpx.AsyncClient(headers=headers, cookies=cookies, follow_redirects=True, http2=True) as client:
        resp = await client.get("https://gemini.google.com/app")
        print("GET Status Code:", resp.status_code)
        print("Returned Cookies:", dict(resp.cookies))
        new_ts = resp.cookies.get("__Secure-1PSIDTS")
        print("Extracted __Secure-1PSIDTS:", new_ts)

if __name__ == "__main__":
    asyncio.run(test())
