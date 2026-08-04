import asyncio
import json
import httpx
import re
from gemini_client.utils import load_cookies, upload_file

async def test_image_structs():
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

    # 1. Create a dummy image
    img_bytes = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc`\x00\x00\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82'
    
    upload_id = await upload_file(img_bytes)
    print("Upload ID:", upload_id)

    async with httpx.AsyncClient(headers=headers, cookies=cookies, http2=True, follow_redirects=True) as client:
        r = await client.get('https://gemini.google.com/app')
        token_matches = re.findall(r'["\']((?:CAMS|AFW|AG|AH)[a-zA-Z0-9_\-\:]{20,})["\']', r.text)
        token = token_matches[0]
        bl_match = re.search(r'"cfb2h":\s*"([^"]+)"', r.text)
        bl = bl_match.group(1) if bl_match else "boq_assistant-bard-web-server_20260730.21_p0"

        # Step A: First turn - create a conversation_id
        struct1 = [[["Hello"], None, ["", "", ""]]]
        data1 = {"f.req": json.dumps([None, json.dumps(struct1)]), "at": token}
        res1 = await client.post("https://gemini.google.com/_/BardChatUi/data/assistant.lamda.BardFrontendService/StreamGenerate", params={"bl": bl, "rt": "c", "_reqid": "10001"}, data=data1)
        
        # Extract conversation_id from response
        conv_id = None
        resp_id = None
        choice_id = None
        for line in res1.text.splitlines():
            if "wrb.fr" in line:
                try:
                    p = json.loads(line[4:].strip()) if line.startswith(")]}") else json.loads(line)
                    for item in p:
                        if isinstance(item, list) and item[0] == "wrb.fr":
                            body = json.loads(item[2])
                            if len(body) > 1 and body[1] and isinstance(body[1], list):
                                conv_id = body[1][0]
                                if len(body[1]) > 1:
                                    resp_id = body[1][1][0] if body[1][1] else None
                except Exception:
                    pass
        print(f"Acquired Conv ID: {conv_id}, Resp ID: {resp_id}")

        # Step B: Test image query WITH existing conv_id vs WITHOUT conv_id
        test_cases = [
            ("Case 1: WITH conv_id", [
                ["Describe this image", 0, None, [[[upload_id, 1], None, "image.jpg"]]],
                None,
                [conv_id, resp_id, choice_id]
            ]),
            ("Case 2: WITHOUT conv_id (Fresh image context)", [
                ["Describe this image", 0, None, [[[upload_id, 1], None, "image.jpg"]]],
                None,
                ["", "", ""]
            ]),
        ]

        for label, msg_struct in test_cases:
            data = {"f.req": json.dumps([None, json.dumps(msg_struct)]), "at": token}
            res = await client.post("https://gemini.google.com/_/BardChatUi/data/assistant.lamda.BardFrontendService/StreamGenerate", params={"bl": bl, "rt": "c", "_reqid": "20002"}, data=data)
            print(f"\n--- Testing {label} ---")
            print("Status:", res.status_code)
            print("Response length:", len(res.text))
            has_wrb_text = "wrb.fr" in res.text and len(res.text) > 500
            print("Has valid wrb.fr payload with text:", has_wrb_text)
            print("Response snippet:", res.text[:250])

if __name__ == "__main__":
    asyncio.run(test_image_structs())
