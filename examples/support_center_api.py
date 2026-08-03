# -*- coding: utf-8 -*-
"""
examples/support_center_api.py
===============================
Multi-User Customer Support Center API Demo using Gemini Unofficial Client.

Demonstrates:
  1. Multi-User Session Isolation: Each customer (`cust_101`, `cust_102`, `cust_103`)
     has an isolated conversation memory session.
  2. Concurrent Support Handling: Customers can ask questions simultaneously;
     their order histories and preferences are never mixed up!
  3. Session Auto-Persistence: Customers returning after hours automatically resume
     their support context.
  4. System Instructions: Global customer support policy ("You are Customer Care AI for StoreX").

Usage:
  python examples/support_center_api.py --auto-cookie
"""
import argparse
import asyncio
import sys
import io
from pathlib import Path

# Force UTF-8 encoding for Windows stdout/stderr
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add project root directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gemini_client import Chatbot, Model, MultiUserMemoryManager


def main():
    parser = argparse.ArgumentParser(description="Multi-User Support Center API Demo")
    parser.add_argument("--cookies", default="cookies.json", help="Path to cookies JSON file")
    parser.add_argument("--auto-cookie", action="store_true", help="Auto-extract cookies from browser")
    args = parser.parse_args()

    print("\n🏢 Initializing Customer Support Center System...")
    bot = Chatbot(
        cookie_path=args.cookies,
        auto_cookie=args.auto_cookie,
        model=Model.G_2_5_FLASH,
    )

    # Initialize Multi-User Support Memory Pool with Global Support Policy
    support_memory = MultiUserMemoryManager(
        default_system_instruction=(
            "You are an empathetic, professional Customer Care AI for 'StoreX Online'. "
            "Help customers with order inquiries, returns, and account questions."
        )
    )

    print("✅ Support Memory Pool Ready!\n" + "─" * 60)

    # ── Simulation: Customer 101 (Order Inquiry) ──────────────────────────────
    print("\n📩 [Customer 101]: 'Hi! My order #4029 is delayed. Can you check?'")
    resp1 = support_memory.ask_user(bot, user_id="cust_101", message="Hi! My order #4029 is delayed. Can you check?")
    print(f"🤖 Support Bot -> [cust_101]:\n{resp1.text}\n")

    # ── Simulation: Customer 102 (Password Reset) ─────────────────────────────
    print("📩 [Customer 102]: 'I forgot my password. How do I reset it?'")
    resp2 = support_memory.ask_user(bot, user_id="cust_102", message="I forgot my password. How do I reset it?")
    print(f"🤖 Support Bot -> [cust_102]:\n{resp2.text}\n")

    # ── Simulation: Customer 101 Follow-up (Tests Memory Isolation!) ─────────
    print("📩 [Customer 101 Follow-up]: 'What order number did I ask about earlier?'")
    resp3 = support_memory.ask_user(bot, user_id="cust_101", message="What order number did I ask about earlier?")
    print(f"🤖 Support Bot -> [cust_101]:\n{resp3.text}\n")

    # ── Simulation: Customer 102 Follow-up ────────────────────────────────────
    print("📩 [Customer 102 Follow-up]: 'Did I mention any order number?'")
    resp4 = support_memory.ask_user(bot, user_id="cust_102", message="Did I mention any order number?")
    print(f"🤖 Support Bot -> [cust_102]:\n{resp4.text}\n")

    # Inspect active support sessions
    print("─" * 60)
    print(f"📊 Active Customer Sessions in Memory: {support_memory.list_active_users()}")
    for uid in support_memory.list_active_users():
        mem = support_memory.get_user_memory(uid)
        print(f"  • User '{uid}': {len(mem.messages)} turns recorded (Saved to: {mem._resolve_path(mem.session_name)})")


if __name__ == "__main__":
    main()
