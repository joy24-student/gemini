import subprocess
import os
import sys

def main():
    subprocess.run([sys.executable, "-m", "pip", "install", "bardapi", "gemini_webapi", "curl_cffi"])
    import bardapi
    path = os.path.dirname(bardapi.__file__)
    print("Bard API path:", path)
    os.system(f"grep -r 'image_upload_id' {path}")
    
    try:
        import gemini_webapi
        path2 = os.path.dirname(gemini_webapi.__file__)
        print("Gemini WebAPI path:", path2)
        os.system(f"grep -r 'image_upload_id' {path2}")
        os.system(f"grep -r 'image' {path2}/core.py")
    except:
        pass

if __name__ == "__main__":
    main()
