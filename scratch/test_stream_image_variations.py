import asyncio
import json
import httpx
import re
from io import BytesIO
from PIL import Image as PILImage
from gemini_client.utils import load_cookies, upload_file

async def test_stream_variations():
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

    # Create real red square image
    img = PILImage.new('RGB', (100, 100), color='red')
    buf = BytesIO()
    img.save(buf, format='PNG')
    img_bytes = buf.getvalue()

    upload_id = await upload_file(img_bytes, cookies=cookies)
    print("Upload ID:", repr(upload_id))

    async with httpx.AsyncClient(headers=headers, cookies=cookies, http2=True, follow_redirects=True) as client:
        r = await client.get('https://gemini.google.com/app')
        token_matches = re.findall(r'["\']((?:CAMS|AFW|AG|AH)[a-zA-Z0-9_\-\:]{20,})["\']', r.text)
        token = token_matches[0]
        bl_match = re.search(r'"cfb2h":\s*"([^"]+)"', r.text)
        bl = bl_match.group(1) if bl_match else "boq_assistant-bard-web-server_20260730.21_p0"

        prompt = "What color is in this image?"

        variations = [
            ("Var 1: [[[upload_id, 1], None, 'image.jpg']]", [
                [prompt, 0, None, [[[upload_id, 1], None, "image.jpg"]]],
                None,
                ["", "", ""]
            ]),
            ("Var 2: [[[upload_id, 1]]]", [
                [prompt, 0, None, [[[upload_id, 1]]]],
                None,
                ["", "", ""]
            ]),
            ("Var 3: [[upload_id, 1]]", [
                [prompt, 0, None, [[upload_id, 1]]],
                None,
                ["", "", ""]
            ]),
            ("Var 4: [[[upload_id, 1], 'image.jpg']]", [
                [prompt, 0, None, [[[upload_id, 1], "image.jpg"]]],
                None,
                ["", "", ""]
            ]),
            ("Var 5: [[[upload_id, 0]]]", [
                [prompt, 0, None, [[[upload_id, 0]]]],
                None,
                ["", "", ""]
            ]),
            ("Var 6: [[[upload_id, 1], None, None, 'image.jpg']]", [
                [prompt, 0, None, [[[upload_id, 1], None, None, "image.jpg"]]],
                None,
                ["", "", ""]
            ]),
            ("Var 7: [[[upload_id, 2]]]", [
                [prompt, 0, None, [[[upload_id, 2]]]],
                None,
                ["", "", ""]
            ]),
        ]

        for label, msg_struct in variations:
            params = {"bl": bl, "rt": "c", "_reqid": "5550001"}
            data = {
                "f.req": json.dumps([None, json.dumps(msg_struct)]),
                "at": token,
            }
            res = await client.post(
                "https://gemini.google.com/_/BardChatUi/data/assistant.lamda.BardFrontendService/StreamGenerate",
                params=params,
                data=data
            )
            print(f"\n--- Testing {label} ---")
            print("Status:", res.status_code)
            
            # Check if response text contains red or color answer
            lines = res.text.splitlines()
            has_red = "red" in res.text.lower()
            print(f"Contains 'red': {has_red}")
            for l in lines:
                if "wrb.fr" in l:
                    print("wrb.fr line preview:", l[:200])

if __name__ == "__main__":
    asyncio.run(test_stream_variations())
