import asyncio
import json
import httpx
import re
from gemini_client.utils import load_cookies, upload_file

async def test_discovery():
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

    # Upload 1x1 test image
    img_bytes = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc`\x00\x00\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82'
    upload_id = await upload_file(img_bytes, cookies=cookies)
    print("Upload ID:", repr(upload_id))

    async with httpx.AsyncClient(headers=headers, cookies=cookies, http2=True, follow_redirects=True) as client:
        r = await client.get('https://gemini.google.com/app')
        token_matches = re.findall(r'["\']((?:CAMS|AFW|AG|AH)[a-zA-Z0-9_\-\:]{20,})["\']', r.text)
        token = token_matches[0]
        bl_match = re.search(r'"cfb2h":\s*"([^"]+)"', r.text)
        bl = bl_match.group(1) if bl_match else "boq_assistant-bard-web-server_20260730.21_p0"

        prompt = "What color is in this picture?"

        structures = [
            ("Format A: [[prompt, 0, None, [[[upload_id, 1]]]]]", [
                [prompt, 0, None, [[[upload_id, 1]]]],
                None,
                ["", "", ""]
            ]),
            ("Format B: [[prompt, 0, None, [[[upload_id, 1], None, 'image.jpg']]]]", [
                [prompt, 0, None, [[[upload_id, 1], None, "image.jpg"]]],
                None,
                ["", "", ""]
            ]),
            ("Format C: [[prompt, 0, None, [[[upload_id, 1], 'image.jpg']]]]", [
                [prompt, 0, None, [[[upload_id, 1], "image.jpg"]]],
                None,
                ["", "", ""]
            ]),
            ("Format D: [[prompt, 0, None, [[upload_id, 1]]]]", [
                [prompt, 0, None, [[upload_id, 1]]],
                None,
                ["", "", ""]
            ]),
            ("Format E: [[prompt, 0, None, [upload_id]]]", [
                [prompt, 0, None, [upload_id]],
                None,
                ["", "", ""]
            ]),
            ("Format F: [[[prompt], None, ['', '', '']], [[[upload_id, 1]]]]", [
                [[prompt], None, ["", "", ""]],
                [[[upload_id, 1]]]
            ]),
            ("Format G: [[prompt, 0, None, [[[upload_id]]]]]", [
                [prompt, 0, None, [[[upload_id]]]],
                None,
                ["", "", ""]
            ]),
            ("Format H: [[prompt, 0, None, [[[upload_id, 1], 1]]]]", [
                [prompt, 0, None, [[[upload_id, 1], 1]]],
                None,
                ["", "", ""]
            ]),
        ]

        for label, msg_struct in structures:
            params = {"bl": bl, "rt": "c", "_reqid": "9990001"}
            data = {
                "f.req": json.dumps([None, json.dumps(msg_struct)]),
                "at": token,
            }
            res = await client.post(
                "https://gemini.google.com/_/BardChatUi/data/assistant.lamda.BardFrontendService/StreamGenerate",
                params=params,
                data=data
            )
            print(f"{label} -> Status: {res.status_code}, Length: {len(res.text)}")
            if res.status_code == 200:
                has_text = "wrb.fr" in res.text and len(res.text) > 400
                print(f"  -> Has wrb.fr payload with text: {has_text}")
                if has_text:
                    print("  🎉 SUCCESSFUL IMAGE STRUCTURE FOUND!", label)
                    print("  Snippet:", res.text[:300])
                    break

if __name__ == "__main__":
    asyncio.run(test_discovery())
