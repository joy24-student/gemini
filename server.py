# -*- coding: utf-8 -*-
"""
server.py
=========
Self-Hosted AI Studio Web Dashboard & OpenAI-Compatible API Gateway Server.

Usage:
  python server.py [--host 0.0.0.0] [--port 8000]

Features:
  1. AI Studio Web UI: Open http://localhost:8000 in browser to manage cookies, API keys, and test prompts.
  2. OpenAI-Compatible API: Use base_url="http://localhost:8000/v1" with standard openai client.
"""
import argparse
import sys
import io
import uvicorn

# Force UTF-8 encoding for Windows stdout/stderr
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from gemini_client.server import app


def main():
    parser = argparse.ArgumentParser(description="Gemini Unofficial AI Studio Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host interface to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    args = parser.parse_args()

    print(f"\n{'='*65}")
    print("  ⚡ Gemini Unofficial AI Studio Web Dashboard & API Server")
    print(f"{'='*65}")
    print(f"  🌐 AI Studio Web Dashboard:  http://localhost:{args.port}")
    print(f"  🔗 OpenAI Base URL:           http://localhost:{args.port}/v1")
    print(f"  📖 Interactive API Docs:     http://localhost:{args.port}/docs")
    print(f"{'='*65}\n")

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
