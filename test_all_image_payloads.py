import asyncio
import json
import httpx
import re
from gemini_client.utils import load_cookies, upload_file

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

    # 1. Upload dummy PNG image
    img_bytes = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc`\x00\x00\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82'
    clean_id = await upload_file(img_bytes)
    print("Clean Upload ID:", repr(clean_id))

    async with httpx.AsyncClient(headers=headers, cookies=cookies, http2=True, follow_redirects=True) as client:
        r = await client.get('https://gemini.google.com/app')
        token_matches = re.findall(r'["\']((?:CAMS|AFW|AG|AH)[a-zA-Z0-9_\-\:]{20,})["\']', r.text)
        token = token_matches[0]
        bl_match = re.search(r'"cfb2h":\s*"([^"]+)"', r.text)
        bl = bl_match.group(1) if bl_match else "boq_assistant-bard-web-server_20260730.21_p0"

        img_struct = [[[clean_id, 1]]]

        # Test placing img_struct at different positions in message_struct
        candidate_payloads = [
            ("P0 (idx 0)", [img_struct, None, ["", "", ""]]),
            ("P1 (idx 1)", [[["Describe image"], img_struct, ["", "", ""]]]),
            ("P2 (idx 3)", [[["Describe image"], None, ["", "", ""], img_struct]]),
            ("P3 (idx 4)", [[["Describe image"], None, ["", "", ""], None, img_struct]]),
            ("P4 (idx 5)", [[["Describe image"], None, ["", "", ""], None, None, img_struct]]),
            ("P5 (idx 6)", [[["Describe image"], None, ["", "", ""], None, None, None, img_struct]]),
        ]

        for label, msg_struct in candidate_payloads:
            params = {"bl": bl, "rt": "c", "_reqid": "7654321"}
            data = {
                "f.req": json.dumps([None, json.dumps(msg_struct)]),
                "at": token,
            }
            res = await client.post("https://gemini.google.com/_/BardChatUi/data/assistant.lamda.BardFrontendService/StreamGenerate", params=params, data=data)
            print(f"Position {label} -> Status: {res.status_code}")
            if res.status_code == 200 and len(res.text) > 100:
                print(f"🎉 SUCCESS WITH IMAGE POSITION {label}!")
                print("Response preview:", res.text[:200])
                break

if __name__ == "__main__":
    asyncio.run(test())
