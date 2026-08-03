# -*- coding: utf-8 -*-
"""
examples/high_scale_500_users_demo.py
======================================
High-Scale Support Engine Demo: Handling 500 Concurrent Users Simultaneously.

Demonstrates:
  1. Concurrency Throttling (`asyncio.Semaphore(500)`): Prevents socket exhaustion under heavy load.
  2. Worker Session Pooling (`AsyncSessionPool`): Load balances queries across pooled HTTP/2 workers.
  3. LRU Memory Caching (`HighScaleMemoryPool`): Retains active users in RAM while auto-evicting idle sessions.
  4. Non-Blocking Async IO: Disk saves run asynchronously in background (`orjson`).
  5. Strict Individual User Context Isolation: Zero cross-talk between concurrent user requests!

Usage:
  python examples/high_scale_500_users_demo.py --auto-cookie --users 500
"""
import argparse
import asyncio
import time
import sys
import io
from pathlib import Path

# Force UTF-8 encoding for Windows stdout/stderr
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add project root directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gemini_client import HighScaleSupportEngine, Model


async def main():
    parser = argparse.ArgumentParser(description="500 Concurrent Users High-Scale Support Demo")
    parser.add_argument("--cookies", default="cookies.json", help="Path to cookies JSON file")
    parser.add_argument("--auto-cookie", action="store_true", help="Auto-extract cookies from browser")
    parser.add_argument("--users", type=int, default=500, help="Number of concurrent users to simulate (default 500)")
    parser.add_argument("--pool-size", type=int, default=10, help="Worker session pool size (default 10)")
    args = parser.parse_args()

    print(f"\n🚀 Initializing High-Scale Support Engine for {args.users} Concurrent Users...")
    print(f"⚙️  Session Pool Size: {args.pool_size} HTTP/2 Workers")

    engine = HighScaleSupportEngine(
        max_concurrent=args.users,
        worker_pool_size=args.pool_size,
        cookie_path=args.cookies,
        auto_cookie=args.auto_cookie,
        model=Model.G_2_5_FLASH,
        system_instruction="You are Customer Support AI for Acme Store. Be concise.",
    )

    start_init = time.time()
    await engine.initialize()
    print(f"✅ Engine initialized in {time.time() - start_init:.2f}s!")

    # ── Simulate 500 Users Sending Queries Concurrently ───────────────────────
    print(f"\n⚡ Simulating {args.users} Users Submitting Support Queries Simultaneously...")
    start_bench = time.time()

    async def _user_task(idx: int):
        user_id = f"user_{idx:04d}"
        msg = f"Hello! My user id is {user_id} and my query code is #{idx * 7}."
        result = await engine.process_user_query(user_id=user_id, message=msg)
        return result

    # Execute all 500 user tasks in parallel via asyncio.gather()
    tasks = [_user_task(i) for i in range(1, args.users + 1)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    total_time = time.time() - start_bench
    successful = [r for r in results if isinstance(r, dict) and not r["response"].error]

    print("\n" + "─" * 60)
    print(f"📊 HIGH-SCALE BENCHMARK RESULTS:")
    print(f"  • Total Users Processed:  {len(results)}")
    print(f"  • Successful Responses:   {len(successful)} / {args.users}")
    print(f"  • Total Time Taken:       {total_time:.2f} seconds")
    print(f"  • Throughput Rate:        {len(successful) / total_time:.1f} users/sec")
    print(f"  • Active Users in RAM:    {len(engine.memory_pool._ram_cache)}")
    print("─" * 60)

    # Display sample response verifying context isolation
    if successful:
        sample = successful[0]
        print(f"\n🔍 Sample User Result [{sample['user_id']}]:")
        print(f"   Gemini: {sample['text'][:120]}...")

    await engine.close()


if __name__ == "__main__":
    asyncio.run(main())
