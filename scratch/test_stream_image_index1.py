import asyncio
from gemini_client import Chatbot, Model

def test_stream():
    bot = Chatbot(cookie_path="cookies.json", model=Model.G_2_5_FLASH)
    img_bytes = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc`\x00\x00\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82'
    
    print("Testing bot.ask_stream with image...")
    chunks = []
    for chunk in bot.ask_stream("Describe this image", image=img_bytes):
        print(chunk, end="", flush=True)
        chunks.append(chunk)
    full_text = "".join(chunks)
    print(f"\nResult length: {len(full_text)}")
    print("Full text returned:", repr(full_text))

if __name__ == "__main__":
    test_stream()
