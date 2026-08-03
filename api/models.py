# api/models.py
# Vercel Serverless Function — GET /v1/models
import json
from http.server import BaseHTTPRequestHandler


MODELS = [
    {"id": "gemini-2.5-flash",          "object": "model", "owned_by": "google-unofficial"},
    {"id": "gemini-2.5-pro",            "object": "model", "owned_by": "google-unofficial"},
    {"id": "gemini-2.0-flash",          "object": "model", "owned_by": "google-unofficial"},
    {"id": "gemini-2.0-flash-thinking", "object": "model", "owned_by": "google-unofficial"},
    {"id": "gemini-3.0-pro",            "object": "model", "owned_by": "google-unofficial"},
    {"id": "gemini-3.0-flash",          "object": "model", "owned_by": "google-unofficial"},
]


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"object": "list", "data": MODELS}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass
