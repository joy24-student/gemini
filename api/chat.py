# api/chat.py
# Vercel Serverless Function — OpenAI-compatible POST /v1/chat/completions
# Reads credentials from GEMINI_1PSID and GEMINI_1PSIDTS environment variables.

import json
import os
import sys
import asyncio
from http.server import BaseHTTPRequestHandler

# ── Bootstrap path so gemini_client is importable inside Vercel ───────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gemini_client import AsyncChatbot, Model


def _get_cookies():
    """Read Google session cookies from Vercel environment variables."""
    psid   = os.environ.get("GEMINI_1PSID", "")
    psidts = os.environ.get("GEMINI_1PSIDTS", "")
    if not psid:
        raise RuntimeError(
            "GEMINI_1PSID environment variable is not set. "
            "Run: vercel env add GEMINI_1PSID"
        )
    return psid, psidts


async def _ask(message: str, model_name: str) -> str:
    """Create a one-shot AsyncChatbot and return the response text."""
    psid, psidts = _get_cookies()

    # Map OpenAI-style model name to Model enum
    model_map = {
        "gemini-2.5-flash":         Model.G_2_5_FLASH,
        "gemini-2.5-pro":           Model.G_2_5_PRO,
        "gemini-2.0-flash":         Model.G_2_0_FLASH,
        "gemini-3.0-pro":           Model.GEMINI_3_0_PRO,
        "gemini-3.0-flash":         Model.GEMINI_3_0_FLASH,
    }
    model = model_map.get(model_name, Model.G_2_5_FLASH)

    bot = await AsyncChatbot.create(psid, psidts, model=model)
    try:
        response = await bot.ask(message)
        return response.text or ""
    finally:
        await bot.session.aclose()


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        # Read body
        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length)

        try:
            req = json.loads(body)
        except Exception:
            self._send(400, {"error": "Invalid JSON body"})
            return

        messages   = req.get("messages", [])
        model_name = req.get("model", "gemini-2.5-flash")

        # Flatten messages into a single prompt
        parts = []
        for msg in messages:
            role    = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                parts.append(f"[System Instruction]\n{content}")
            elif role == "assistant":
                parts.append(f"Assistant: {content}")
            else:
                parts.append(f"User: {content}")
        prompt = "\n".join(parts)

        try:
            text = asyncio.run(_ask(prompt, model_name))
        except RuntimeError as e:
            self._send(500, {"error": {"message": str(e), "type": "server_error"}})
            return
        except Exception as e:
            self._send(502, {"error": {"message": f"Gemini error: {e}", "type": "upstream_error"}})
            return

        import time, secrets
        response_body = {
            "id":      f"chatcmpl-{secrets.token_hex(12)}",
            "object":  "chat.completion",
            "created": int(time.time()),
            "model":   model_name,
            "choices": [
                {
                    "index":         0,
                    "message":       {"role": "assistant", "content": text},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens":     0,
                "completion_tokens": 0,
                "total_tokens":      0,
            },
        }
        self._send(200, response_body)

    def do_GET(self):
        self._send(405, {"error": "Method Not Allowed — use POST"})

    def _send(self, status: int, body: dict):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass  # suppress default access logs in Vercel output
