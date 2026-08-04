# -*- coding: utf-8 -*-
"""
server.py
=========
Self-Hosted AI Studio Web Dashboard & OpenAI-Compatible API Gateway Server.

Usage:
  python server.py [--host 0.0.0.0] [--port 8000] [--auto-port]

Features:
  1. AI Studio Web UI: Open http://localhost:8000 in browser to manage cookies, API keys, and test prompts.
  2. OpenAI-Compatible API: Use base_url="http://localhost:8000/v1" with standard openai client.
  3. Auto Port Fallback: Automatically selects an open port if port 8000 is occupied.
"""
import argparse
import sys
import io
import os
import socket
import uvicorn

# Force UTF-8 encoding for Windows stdout/stderr
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from gemini_client.server import app


def is_port_available(host: str, port: int) -> bool:
    """Check if a host:port combination is available for binding."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def find_available_port(host: str, start_port: int, max_attempts: int = 50) -> int:
    """Find the first available port starting from start_port."""
    for p in range(start_port, start_port + max_attempts):
        if is_port_available(host, p):
            return p
    return start_port


def main():
    parser = argparse.ArgumentParser(description="Gemini Unofficial AI Studio Server")
    parser.add_argument("--host", default=os.environ.get("HOST", "0.0.0.0"), help="Host interface to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)), help="Port to listen on (default: 8000)")
    parser.add_argument("--no-auto-port", action="store_true", help="Disable automatic port fallback if port is in use")
    args = parser.parse_args()

    target_port = args.port

    # Auto fallback if target port is occupied
    if not is_port_available(args.host, target_port):
        if not args.no_auto_port:
            fallback_port = find_available_port(args.host, target_port + 1)
            print(f"\n⚠️  [NOTICE] Port {target_port} is already in use by another process.")
            print(f"🔄 [AUTO-FALLBACK] Binding to next available port: {fallback_port}\n")
            target_port = fallback_port
        else:
            print(f"\n❌ [ERROR] Port {target_port} is in use. Terminate the existing process or run with --port <new_port>\n")
            sys.exit(1)

    print(f"\n{'='*65}")
    print("  ⚡ Gemini Unofficial AI Studio Web Dashboard & API Server")
    print("  Created by Joy Saha (https://sahajoy.vercel.app/)")
    print(f"{'='*65}")
    print(f"  🌐 AI Studio Web Dashboard:  http://localhost:{target_port}")
    print(f"  🔗 OpenAI Base URL:           http://localhost:{target_port}/v1")
    print(f"  📖 Interactive API Docs:     http://localhost:{target_port}/docs")
    print(f"{'='*65}\n")

    uvicorn.run(app, host=args.host, port=target_port)


if __name__ == "__main__":
    main()
