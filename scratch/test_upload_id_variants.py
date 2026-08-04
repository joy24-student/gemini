import asyncio
import json
import httpx
import re
from io import BytesIO
from PIL import Image as PILImage
from gemini_client.utils import load_cookies, upload_file

async def test_variants():
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

    # Create real image
    img = PILImage.new('RGB', (100, 100), color='blue')
    buf = BytesIO()
    img.save(buf, format='PNG')
    img_bytes = buf.getvalue()

    upload_id = await upload_file(img_bytes, cookies=cookies)
    print("Raw Upload ID:", repr(upload_id))

    # Variants of upload_id
    # 1. /contrib_service/ttl_1d/xyz
    # 2. contrib_service/ttl_1d/xyz
    # 3. xyz (basename)
    # 4. https://lh3.googleusercontent.com/contrib_service/ttl_1d/xyz
    filename = upload_id.split("/")[-1]

    id_variants = [
        ("Raw ID", upload_id),
        ("No leading slash", upload_id.lstrip("/")),
        ("Filename only", filename),
        ("Full URL", f"https://lh3.googleusercontent.com{upload_id}"),
    ]

    async with httpx.AsyncClient(headers=headers, cookies=cookies, http2=True, follow_redirects=True) as client:
        r = await client.get('https://gemini.google.com/app')
        token_matches = re.findall(r'["\']((?:CAMS|AFW|AG|AH)[a-zA-Z0-9_\-\:]{20,})["\']', r.text)
        token = token_matches[0]
        bl_match = re.search(r'"cfb2h":\s*"([^"]+)"', r.text)
        bl = bl_match.group(1) if bl_match else "boq_assistant-bard-web-server_20260730.21_p0"

        prompt = "What color is this image?"

        for var_name, vid in id_variants:
            msg_struct = [
                [prompt, 0, None, [[[vid, 1], None, "image.jpg"]]],
                None,
                ["", "", ""]
            ]
            params = {"bl": bl, "rt": "c", "_reqid": "8880001"}
            data = {
                "f.req": json.dumps([None, json.dumps(msg_struct)]),
                "at": token,
            }
            res = await client.post(
                "https://gemini.google.com/_/BardChatUi/data/assistant.lamda.BardFrontendService/StreamGenerate",
                params=params,
                data=data
            )
            print(f"\n--- Testing Variant: {var_name} ({vid}) ---")
            print("Status:", res.status_code)
            has_blue = "blue" in res.text.lower()
            print("Contains 'blue':", has_blue)
            print("Snippet:", res.text[:250])

if __name__ == "__main__":
    asyncio.run(test_variants())
