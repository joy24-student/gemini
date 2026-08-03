# -*- coding: utf-8 -*-
"""
examples/unofficial_image_chat.py
=================================
Unofficial Gemini Image Analysis Example (Zero API Key Needed).

Uploads an image file to Google's internal content-push endpoint
via cookie authentication and asks Gemini Web UI to analyze it.

Usage:
  python examples/unofficial_image_chat.py --image path/to/image.jpg --auto-cookie
"""
import argparse
import os

from gemini_client import Chatbot, Model


def main():
    parser = argparse.ArgumentParser(description="Unofficial Gemini Image Chat")
    parser.add_argument("--image", required=True, help="Path to image file (jpg, png, webp)")
    parser.add_argument("--prompt", default="Describe this image in detail and list key objects in it.", help="Prompt text")
    parser.add_argument("--cookies", default="cookies.json", help="Path to cookies JSON file")
    parser.add_argument("--auto-cookie", action="store_true", help="Auto-extract cookies from browser")
    args = parser.parse_args()

    if not os.path.exists(args.image):
        print(f"❌ Image file not found: {args.image}")
        return

    print("Initializing Unofficial Gemini Chatbot...")
    if args.auto_cookie:
        bot = Chatbot(auto_cookie=True, model=Model.G_2_5_FLASH)
    else:
        bot = Chatbot(cookie_path=args.cookies, model=Model.G_2_5_FLASH)

    print(f"Uploading and analyzing image: {args.image}")
    response = bot.ask(args.prompt, image=args.image)

    if response.error:
        print(f"❌ Error: {response.error_message}")
    else:
        print(f"\n🤖 Gemini: {response.text}\n")
        if response.images:
            print("Extracted image links in response:")
            for img in response.images:
                print(f" - {img.get('url')}")


if __name__ == "__main__":
    main()
