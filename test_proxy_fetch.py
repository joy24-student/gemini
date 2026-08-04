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

async def test_fetch(test_url):
    print("Testing fetch for URL:", test_url)
    
    # Ensure https:// scheme
    if test_url.startswith("http://"):
        test_url = "https://" + test_url[7:]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://gemini.google.com/",
        "Origin": "https://gemini.google.com",
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    }
    
    cookies = {}
    if env_psid: cookies["__Secure-1PSID"] = env_psid
    if env_psidts: cookies["__Secure-1PSIDTS"] = env_psidts

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers=headers, cookies=cookies, http2=True) as client:
            resp = await client.get(test_url)
            print("Status code:", resp.status_code)
            print("Headers:", dict(resp.headers))
            print("Content length:", len(resp.content))
            return resp.status_code == 200
    except Exception as e:
        print("Fetch exception:", type(e), e)
        return False

if __name__ == "__main__":
    url = "http://googleusercontent.com/image_generation_content/431"
    asyncio.run(test_fetch(url))
