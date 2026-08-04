import asyncio
from io import BytesIO
from PIL import Image as PILImage
from gemini_client import Chatbot, Model

def test_real_image():
    # Generate real 100x100 red PNG image
    img = PILImage.new('RGB', (100, 100), color='red')
    buf = BytesIO()
    img.save(buf, format='PNG')
    img_bytes = buf.getvalue()

    bot = Chatbot(cookie_path="cookies.json", model=Model.G_2_5_FLASH)
    print("Testing real image stream...")
    chunks = []
    for chunk in bot.ask_stream("What color is this image?", image=img_bytes):
        print(chunk, end="", flush=True)
        chunks.append(chunk)
    full_text = "".join(chunks)
    print(f"\nResult length: {len(full_text)}")
    print("Full text returned:", repr(full_text))

if __name__ == "__main__":
    test_real_image()
