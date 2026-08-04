import asyncio
import json
import base64
from gemini_client.core import AsyncChatbot
from gemini_client.utils import upload_file

async def main():
    print("Loading cookies.json...")
    try:
        with open("cookies.json", "r") as f:
            cookies_data = json.load(f)
        if isinstance(cookies_data, list):
            cookies = {}
            for c in cookies_data:
                if c.get("name") in ("__Secure-1PSID", "__Secure-1PSIDTS"):
                    cookies[c["name"]] = c["value"]
        else:
            cookies = cookies_data
    except Exception as e:
        print(f"Failed to load cookies.json: {e}")
        return

    # A simple 1x1 red pixel image in base64
    b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    image_bytes = base64.b64decode(b64)

    print("Uploading image...")
    try:
        image_id = await upload_file(image_bytes, cookies=cookies)
        print(f"Upload returned ID: {image_id}")
    except Exception as e:
        print(f"Upload failed: {e}")
        return

    if not image_id:
        print("Upload ID is empty!")
        return

    print("Initializing AsyncChatbot...")
    bot = await AsyncChatbot.create(cookies.get("__Secure-1PSID"), cookies.get("__Secure-1PSIDTS"))

    print("Sending message with image...")
    try:
        response = await bot.ask("What is the color of this image? Please reply briefly.", image=image_bytes)
        print("Model Response:")
        print(response.text)
    except Exception as e:
        print(f"Model failed: {e}")
    finally:
        await bot.session.aclose()

if __name__ == "__main__":
    asyncio.run(main())
