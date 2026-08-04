import asyncio
import io
import os
import sys
from pathlib import Path

from gemini_client.core import AsyncChatbot
from gemini_client.enums import Model
from gemini_client.utils import load_cookies


if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")


def load_cookie_pair() -> tuple[str, str, str]:
    """Load .env first, falling back to cookies.json."""
    env_path = Path(".env")
    if env_path.is_file():
        for raw_line in env_path.read_text(encoding="utf-8-sig").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() in ("GEMINI_1PSID", "GEMINI_1PSIDTS"):
                os.environ[key.strip()] = value.strip().strip("\"'")

    psid = os.environ.get("GEMINI_1PSID", "").strip()
    psidts = os.environ.get("GEMINI_1PSIDTS", "").strip()
    if psid:
        return psid, psidts, ".env"

    psid, psidts = load_cookies("cookies.json")
    return psid, psidts, "cookies.json"


async def main() -> None:
    print("=" * 60)
    print("GEMINI COOKIE AND FUNCTIONALITY TEST")
    print("=" * 60)

    psid, psidts, source = load_cookie_pair()
    print(f"\n[Step 1] Loading cookies from {source}...")
    if not psid or not psidts:
        raise RuntimeError("Both __Secure-1PSID and __Secure-1PSIDTS are required.")

    bot = await AsyncChatbot.create(
        psid,
        psidts,
        timeout=60,
        model=Model.G_2_5_FLASH,
    )
    try:
        print(f"Gemini account status: {bot.account_status}")
        if bot.account_status != 1000:
            raise RuntimeError(
                f"Cookie authentication failed (Gemini status {bot.account_status})."
            )
        print("Authenticated account status verified.")

        print("\n[Step 2] Testing non-streaming response...")
        response = await bot.ask("Reply with exactly: COOKIE_TEST_OK")
        if response.error or "COOKIE_TEST_OK" not in response.text:
            raise RuntimeError(f"Unexpected non-streaming response: {response.text!r}")
        print("Non-streaming response verified.")

        print("\n[Step 3] Testing streaming response...")
        chunks = []
        async for chunk in bot.ask_stream("Reply with exactly: STREAM_TEST_OK"):
            chunks.append(chunk)
        stream_text = "".join(chunks)
        if "STREAM_TEST_OK" not in stream_text:
            raise RuntimeError(f"Unexpected streaming response: {stream_text!r}")
        print("Streaming response verified.")

        print("\nALL TESTS PASSED: COOKIES ARE AUTHENTICATED.")
    finally:
        await bot.session.aclose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print(f"\nTEST FAILED: {exc}")
        raise SystemExit(1)
