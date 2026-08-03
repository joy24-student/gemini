# api/health.py
# Vercel Serverless Function — GET /health
import json
import os
from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        has_cookie = bool(os.environ.get("GEMINI_1PSID"))
        body = json.dumps({
            "status":  "ready" if has_cookie else "degraded",
            "cookies": "configured" if has_cookie else "missing — set GEMINI_1PSID env var",
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass
