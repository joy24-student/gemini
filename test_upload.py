import asyncio
from gemini_client.cookie_manager import CookieExtractor
from gemini_client.utils import upload_file

async def test_upload():
    extractor = CookieExtractor()
    cookies = extractor.extract_cookies(save_to_disk=False)
    psid = cookies.get('__Secure-1PSID')
    psidts = cookies.get('__Secure-1PSIDTS')
    
    if not psid:
        print("No cookies found!")
        return

    cookie_dict = {'__Secure-1PSID': psid, '__Secure-1PSIDTS': psidts}
    
    # Create a dummy 1x1 PNG image
    dummy_png = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0bIDAT\x08\x99c\xf8\x0f\x04\x00\t\xfb\x03\xfd\xe3U\xf2\x9c\x00\x00\x00\x00IEND\xaeB`\x82'
    
    print("Uploading dummy image to Google...")
    try:
        upload_id = await upload_file(dummy_png, cookies=cookie_dict)
        print(f"Upload returned ID: {upload_id}")
    except Exception as e:
        print(f"Upload failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_upload())
