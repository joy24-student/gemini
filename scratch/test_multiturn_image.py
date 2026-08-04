import asyncio
from gemini_client import Chatbot, Model

def test_multiturn():
    bot = Chatbot(cookie_path="cookies.json", model=Model.G_2_5_FLASH)
    print("--- Turn 1: Text message ---")
    r1 = bot.ask("Hello")
    print("Turn 1 Response:", r1.text[:100])
    print("Conversation ID:", bot.async_chatbot.conversation_id)

    print("\n--- Turn 2: Image message with existing conversation_id ---")
    img_bytes = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc`\x00\x00\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82'
    
    chunks = []
    print("Stream output for Turn 2:")
    for chunk in bot.ask_stream("Describe this image", image=img_bytes):
        print(chunk, end="", flush=True)
        chunks.append(chunk)
    print("\nTotal text length returned in Turn 2:", len("".join(chunks)))

if __name__ == "__main__":
    test_multiturn()
