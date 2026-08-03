import asyncio
import sys
import io
import httpx
import re
import json
from gemini_client.utils import load_cookies

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

async def test():
    psid, psidts = load_cookies('cookies.json')
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Origin': 'https://gemini.google.com',
        'Referer': 'https://gemini.google.com/',
        'Content-Type': 'application/x-www-form-urlencoded;charset=utf-8',
        'X-Same-Domain': '1',
    }
    cookies = {'__Secure-1PSID': psid}
    if psidts:
        cookies['__Secure-1PSIDTS'] = psidts

    async with httpx.AsyncClient(headers=headers, cookies=cookies, http2=True, follow_redirects=True) as client:
        r = await client.get('https://gemini.google.com/app')
        text = r.text
        
        wiz_match = re.search(r'WIZ_global_data\s*=\s*(\{.*?\});', text, re.DOTALL)
        if not wiz_match:
            print("WIZ_global_data not found")
            return
        
        data = json.loads(wiz_match.group(1))
        bl = data.get("cfb2h", "boq_assistant-bard-web-server_20260730.21_p0")
        
        # Test candidate tokens
        candidates = []
        if "SNlM0e" in data:
            candidates.append(("SNlM0e", data["SNlM0e"]))
        for k, v in data.items():
            if isinstance(v, str) and len(v) > 20 and ("AF" in v or "AG" in v or "AH" in v or "AI" in v):
                candidates.append((k, v))
        
        print(f"Testing {len(candidates)} candidate tokens on StreamGenerate endpoint...")
        message_struct = [["Hello, reply with 'OK'"], None, ["", "", ""]]
        
        for k, token in candidates:
            params = {"bl": bl, "rt": "c", "_reqid": "1234567"}
            req_data = {
                "f.req": json.dumps([None, json.dumps(message_struct)]),
                "at": token,
            }
            try:
                gen_resp = await client.post("https://gemini.google.com/_/BardChatUi/data/assistant.lamda.BardFrontendService/StreamGenerate", params=params, data=req_data, timeout=10.0)
                print(f"Token key '{k}' ({token[:20]}...) -> Status: {gen_resp.status_code}, Length: {len(gen_resp.text)}")
                if gen_resp.status_code == 200 and len(gen_resp.text) > 100:
                    print(f"🎉 SUCCESS! Token key '{k}' is the valid session token!")
                    print("Sample response:", gen_resp.text[:200])
                    break
            except Exception as e:
                print(f"Token key '{k}' failed: {e}")

if __name__ == '__main__':
    asyncio.run(test())
