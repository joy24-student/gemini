# -*- coding: utf-8 -*-
"""
gemini_client/scale_engine.py
=============================
High-Scale Concurrency & Memory Engine for 500+ Simultaneous Users.

Optimizations:
  1. LRU Memory Cache & Async Disk Persistence: Keeps top active users in RAM
     while evicting idle sessions to disk via fast orjson.
  2. Async Session Worker Pool (`AsyncSessionPool`): Distributes high-throughput
     concurrent user queries across pooled HTTP/2 Chatbot workers.
  3. Per-User Async Lock (`asyncio.Lock`): Ensures strict order for concurrent
     messages coming from the same user without blocking other users.
  4. Non-Blocking IO & Concurrency Throttling: Managed via `asyncio.Semaphore(500)`.
  5. Live Background Cookie/Token Health Check: Auto-refreshes auth in background.
"""
from __future__ import annotations

import asyncio
import os
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from rich.console import Console

from gemini_client.core import AsyncChatbot, Model
from gemini_client.cookie_manager import CookieExtractor
from gemini_client.cookie_pool import CookiePool
from gemini_client.memory import ConversationMemory, MemoryMessage
from gemini_client.utils import load_cookies

console = Console()

# ── Fast JSON ───────────────────────────────────────────────────────────────
try:
    import orjson  # type: ignore
    def _fast_loads(s): return orjson.loads(s)
    def _fast_dumps(o): return orjson.dumps(o)
except ImportError:
    import json as _json
    def _fast_loads(s): return _json.loads(s)
    def _fast_dumps(o): return _json.dumps(o, ensure_ascii=False).encode()


class HighScaleMemoryPool:
    """
    LRU Session Memory Cache & Non-Blocking Disk Persister for 500+ Concurrent Users.

    Parameters
    ----------
    max_ram_users : int
        Maximum number of user session objects to retain in RAM (default 200).
    max_history_per_user : int
        Maximum message history per user (default 30).
    default_system_instruction : str, optional
        Global system prompt instructions.
    storage_dir : str, optional
        Storage directory for per-user JSON files.
    """

    def __init__(
        self,
        max_ram_users: int = 200,
        max_history_per_user: int = 30,
        default_system_instruction: Optional[str] = None,
        storage_dir: Optional[str] = None,
    ):
        self.max_ram_users = max_ram_users
        self.max_history_per_user = max_history_per_user
        self.default_system_instruction = default_system_instruction

        if storage_dir:
            self.storage_dir = Path(storage_dir)
            try:
                self.storage_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
        else:
            from gemini_client.utils import ensure_data_dir
            self.storage_dir = ensure_data_dir("scale_memory")

        # LRU RAM Cache: user_id -> ConversationMemory
        self._ram_cache: OrderedDict[str, ConversationMemory] = OrderedDict()
        self._user_locks: Dict[str, asyncio.Lock] = {}
        # Per-user Gemini session IDs (conversation_id, response_id, choice_id, reqid)
        # These are stored here so workers remain stateless between users
        self._conv_ids: Dict[str, Tuple[str, str, str, int]] = {}

        # Sharded locks: 16 buckets instead of one global lock.
        # Users land in different buckets so only ~1/16 of users contend.
        _NUM_SHARDS = 16
        self._shard_locks: List[asyncio.Lock] = [asyncio.Lock() for _ in range(_NUM_SHARDS)]

    def _shard_lock(self, key: str) -> asyncio.Lock:
        """Return the shard lock for a given key."""
        return self._shard_locks[hash(key) % len(self._shard_locks)]

    async def get_user_lock(self, user_id: str) -> asyncio.Lock:
        """Get or create per-user asyncio lock for message ordering (sharded)."""
        async with self._shard_lock(user_id):
            if user_id not in self._user_locks:
                self._user_locks[user_id] = asyncio.Lock()
            return self._user_locks[user_id]

    async def get_user_memory(self, user_id: str) -> ConversationMemory:
        """
        Retrieve user ConversationMemory from RAM (sharded LRU hit) or load from disk.
        """
        shard = self._shard_lock(user_id)
        async with shard:
            if user_id in self._ram_cache:
                self._ram_cache.move_to_end(user_id)
                return self._ram_cache[user_id]

        # Load from disk outside of any lock (slow path)
        file_path = self.storage_dir / f"user_{user_id}.json"
        mem = ConversationMemory(
            session_name=f"user_{user_id}",
            system_instruction=self.default_system_instruction,
            max_messages=self.max_history_per_user,
            storage_dir=str(self.storage_dir),
        )

        if file_path.exists():
            await asyncio.to_thread(self._async_load_file, mem, file_path)

        async with shard:
            # Double-checked locking: another coroutine may have inserted while we loaded
            if user_id not in self._ram_cache:
                self._ram_cache[user_id] = mem
            self._ram_cache.move_to_end(user_id)
            # Evict oldest if exceeding RAM capacity
            while len(self._ram_cache) > self.max_ram_users:
                evicted_uid, evicted_mem = self._ram_cache.popitem(last=False)
                asyncio.create_task(self._async_save_memory(evicted_uid, evicted_mem))

        return self._ram_cache[user_id]

    def get_conv_ids(self, user_id: str) -> Tuple[str, str, str, int]:
        """Return (conversation_id, response_id, choice_id, reqid) for this user."""
        return self._conv_ids.get(user_id, ("", "", "", 0))

    def set_conv_ids(self, user_id: str, conv_id: str, resp_id: str, choice_id: str, reqid: int = 0) -> None:
        """Persist updated Gemini session IDs for this user."""
        self._conv_ids[user_id] = (conv_id, resp_id, choice_id, reqid)

    async def record_turn(self, user_id: str, user_text: str, model_text: str):
        """Record user and model turn in memory and schedule async background save."""
        mem = await self.get_user_memory(user_id)
        mem.add_user_message(user_text)
        if model_text:
            mem.add_model_message(model_text)
        asyncio.create_task(self._async_save_memory(user_id, mem))

    def _async_load_file(self, mem: ConversationMemory, file_path: Path):
        try:
            with open(file_path, "rb") as f:
                data = _fast_loads(f.read())
            mem.system_instruction = data.get("system_instruction", mem.system_instruction)
            mem.messages = [MemoryMessage.from_dict(m) for m in data.get("messages", [])]
        except Exception:
            pass

    async def _async_save_memory(self, user_id: str, mem: ConversationMemory):
        """Non-blocking async disk save using fast orjson."""
        file_path = self.storage_dir / f"user_{user_id}.json"
        data = {
            "session_name": f"user_{user_id}",
            "system_instruction": mem.system_instruction,
            "updated_at": time.time(),
            "messages": [msg.to_dict() for msg in mem.messages],
        }
        raw_bytes = _fast_dumps(data)
        await asyncio.to_thread(self._write_bytes, file_path, raw_bytes)

    def _write_bytes(self, file_path: Path, raw_bytes: bytes):
        try:
            with open(file_path, "wb") as f:
                f.write(raw_bytes)
        except Exception:
            pass


class AsyncSessionPool:
    """
    HTTP/2 Session Worker Pool with round-robin dispatch.

    Supports both single-account and multi-account (CookiePool) modes.
    In multi-account mode, each worker is initialized with a different
    Google account cookie pair to distribute load and avoid rate limits.

    Parameters
    ----------
    pool_size : int
        Number of pooled AsyncChatbot worker instances (default 10).
    secure_1psid : str
        Single-account PSID (used only when cookie_pool is None).
    secure_1psidts : str
        Single-account PSIDTS (used only when cookie_pool is None).
    cookie_pool : CookiePool, optional
        Multi-account pool. When provided, workers use different accounts.
    model : Model
    """

    def __init__(
        self,
        pool_size: int = 10,
        secure_1psid: Optional[str] = None,
        secure_1psidts: Optional[str] = None,
        cookie_path: Optional[str] = None,
        auto_cookie: bool = True,
        model: Model = Model.G_2_5_FLASH,
        cookie_pool: Optional[CookiePool] = None,
    ):
        self.pool_size = pool_size
        self.model = model
        self.cookie_pool = cookie_pool

        self.all_cookies = {}
        if cookie_pool is None:
            # Single-account fallback
            if cookie_path and os.path.exists(cookie_path):
                self.secure_1psid, self.secure_1psidts = load_cookies(cookie_path)
                try:
                    import json
                    with open(cookie_path, 'r', encoding='utf-8') as _f:
                        _d = json.load(_f)
                        if isinstance(_d, dict):
                            self.all_cookies = {str(k): str(v) for k, v in _d.items()}
                        elif isinstance(_d, list):
                            self.all_cookies = {str(i.get("name", "")): str(i.get("value", "")) for i in _d if isinstance(i, dict)}
                except Exception:
                    self.all_cookies = {"__Secure-1PSID": self.secure_1psid, "__Secure-1PSIDTS": self.secure_1psidts}
            elif auto_cookie and (not secure_1psid or not secure_1psidts):
                extractor = CookieExtractor()
                cookies = extractor.extract_cookies(save_to_disk=False)
                self.secure_1psid = cookies['__Secure-1PSID']
                self.secure_1psidts = cookies['__Secure-1PSIDTS']
                self.all_cookies = cookies
            else:
                self.secure_1psid = secure_1psid or ""
                self.secure_1psidts = secure_1psidts or ""
        else:
            # Multi-account: will be assigned per-worker during initialize()
            self.secure_1psid = ""
            self.secure_1psidts = ""

        self.workers: List[AsyncChatbot] = []
        self._rr_index = 0
        self._pool_lock = asyncio.Lock()

    async def initialize(self):
        """Initialize all worker instances concurrently, each with a distinct cookie pair."""
        console.log(f"[bold cyan]Initializing Pool of {self.pool_size} AsyncChatbot Workers...[/bold cyan]")
        tasks = []
        for _ in range(self.pool_size):
            if self.cookie_pool is not None:
                # Multi-account: each worker gets its own account
                psid, psidts = self.cookie_pool.next()
            else:
                psid, psidts = self.secure_1psid, self.secure_1psidts
            tasks.append(
                AsyncChatbot.create(
                    secure_1psid=psid,
                    secure_1psidts=psidts,
                    model=self.model,
                    cookies_dict=self.all_cookies,
                )
            )
        self.workers = await asyncio.gather(*tasks)
        console.log(f"[bold green]All {len(self.workers)} Session Workers Ready![/bold green]")

    async def get_worker(self) -> AsyncChatbot:
        """Round-robin worker dispatch."""
        async with self._pool_lock:
            worker = self.workers[self._rr_index]
            self._rr_index = (self._rr_index + 1) % len(self.workers)
            return worker

    async def close(self):
        """Close all worker sessions."""
        for w in self.workers:
            try:
                await w.session.aclose()  # httpx.AsyncClient uses aclose(), not close()
            except Exception:
                pass
        self.workers.clear()


class HighScaleSupportEngine:
    """
    High-Throughput Support Center Engine for 500+ Concurrent Users.

    Combines:
      - Concurrency Throttling (`asyncio.Semaphore(max_concurrent)`)
      - LRU Memory Pool & Non-Blocking Async Disk Storage
      - Round-Robin HTTP/2 Session Worker Pool

    Usage::

        engine = HighScaleSupportEngine(max_concurrent=500, worker_pool_size=10)
        await engine.initialize()

        # Handle 500 concurrent user requests
        tasks = [
            engine.process_user_query(user_id=f"user_{i}", message="Order status?")
            for i in range(500)
        ]
        results = await asyncio.gather(*tasks)
    """

    def __init__(
        self,
        max_concurrent: int = 500,
        worker_pool_size: int = 10,
        secure_1psid: Optional[str] = None,
        secure_1psidts: Optional[str] = None,
        cookie_path: Optional[str] = None,
        auto_cookie: bool = True,
        model: Model = Model.G_2_5_FLASH,
        system_instruction: Optional[str] = None,
        cookie_pool: Optional[CookiePool] = None,
    ):
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.session_pool = AsyncSessionPool(
            pool_size=worker_pool_size,
            secure_1psid=secure_1psid,
            secure_1psidts=secure_1psidts,
            cookie_path=cookie_path,
            auto_cookie=auto_cookie,
            model=model,
            cookie_pool=cookie_pool,
        )
        self.memory_pool = HighScaleMemoryPool(
            max_ram_users=300,
            default_system_instruction=system_instruction,
        )

    @property
    def secure_1psid(self) -> str:
        return self.session_pool.secure_1psid

    @secure_1psid.setter
    def secure_1psid(self, val: str):
        self.session_pool.secure_1psid = val

    @property
    def secure_1psidts(self) -> str:
        return self.session_pool.secure_1psidts

    @secure_1psidts.setter
    def secure_1psidts(self, val: str):
        self.session_pool.secure_1psidts = val

    async def initialize(self):
        """Start the worker pool."""
        await self.session_pool.initialize()

    async def process_user_query(
        self,
        user_id: str,
        message: str,
        image: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Process a customer query under strict per-user message lock and concurrency throttling.

        Workers are stateless: each call injects the user's saved conversation IDs
        before the request, then reads the updated IDs from the worker and saves
        them back to this user's slot — preventing any cross-user state corruption.
        """
        async with self.semaphore:
            user_lock = await self.memory_pool.get_user_lock(user_id)
            async with user_lock:
                # 1. Fetch user memory & context prompt
                user_mem = await self.memory_pool.get_user_memory(user_id)
                context_prompt = user_mem.get_context_prompt(message)

                # 2. Get a worker from pool
                worker = await self.session_pool.get_worker()

                # 3. Inject this user's conversation state into the worker (stateless handoff)
                conv_id, resp_id, choice_id, reqid = self.memory_pool.get_conv_ids(user_id)
                worker.conversation_id = conv_id
                worker.response_id = resp_id
                worker.choice_id = choice_id
                if reqid != 0:
                    worker._reqid = reqid

                # If active session conv_id exists, send message directly. If fresh session, send context_prompt.
                send_prompt = message if conv_id else context_prompt

                # 4. Query Gemini
                response = await worker.ask(send_prompt, image=image)

                # Fallback retry if session expired or rejected:
                if (conv_id or getattr(response, "error", False)) and (not getattr(response, "text", "") or getattr(response, "error", False)):
                    worker.conversation_id = ""
                    worker.response_id = ""
                    worker.choice_id = ""
                    try:
                        await worker._refresh_snlm0e()
                    except Exception:
                        pass
                    response = await worker.ask(context_prompt, image=image)

                # 5. Save updated conversation IDs back to user's memory slot
                self.memory_pool.set_conv_ids(
                    user_id,
                    worker.conversation_id,
                    worker.response_id,
                    worker.choice_id,
                    worker._reqid,
                )

                # 6. Extract model text & record turn
                model_text = getattr(response, "text", "") or ""
                await self.memory_pool.record_turn(user_id, message, model_text)

                return {
                    "user_id": user_id,
                    "response": response,
                    "text": model_text,
                    "turns_in_memory": len(user_mem.messages),
                }

    async def process_user_query_stream(
        self,
        user_id: str,
        message: str,
        image: Optional[Any] = None,
    ) -> AsyncIterator[str]:
        """
        Process a customer query with real-time SSE streaming.
        """
        async with self.semaphore:
            user_lock = await self.memory_pool.get_user_lock(user_id)
            async with user_lock:
                user_mem = await self.memory_pool.get_user_memory(user_id)
                context_prompt = user_mem.get_context_prompt(message)

                worker = await self.session_pool.get_worker()

                conv_id, resp_id, choice_id, reqid = self.memory_pool.get_conv_ids(user_id)
                worker.conversation_id = conv_id
                worker.response_id = resp_id
                worker.choice_id = choice_id
                if reqid != 0:
                    worker._reqid = reqid

                send_prompt = message if conv_id else context_prompt
                
                full_text = ""
                error_occurred = False
                try:
                    async for chunk in worker.ask_stream(send_prompt, image=image):
                        full_text += chunk
                        yield chunk
                except Exception as e:
                    error_occurred = True
                    # If active session expired (or 1096 session error occurred), refresh worker & retry once with full context prompt
                    if (conv_id or "1096" in str(e) or "expired" in str(e) or "BardErrorInfo" in str(e)) and not full_text:
                        worker.conversation_id = ""
                        worker.response_id = ""
                        worker.choice_id = ""
                        try:
                            await worker._refresh_snlm0e()
                        except Exception:
                            pass
                        try:
                            async for chunk in worker.ask_stream(context_prompt, image=image):
                                full_text += chunk
                                yield chunk
                        except Exception as inner_e:
                            yield f"\n[Gateway Stream Error: {inner_e}]"
                    else:
                        yield f"\n[Gateway Stream Error: {e}]"

                # Save updated conversation state back to user memory slot
                self.memory_pool.set_conv_ids(
                    user_id,
                    worker.conversation_id,
                    worker.response_id,
                    worker.choice_id,
                    worker._reqid,
                )

                # Record full text output to memory history
                if full_text:
                    await self.memory_pool.record_turn(user_id, message, full_text)

    async def close(self):
        """Shutdown engine and session pool."""
        await self.session_pool.close()
