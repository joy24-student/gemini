# -*- coding: utf-8 -*-
"""
gemini_client/dedup.py
======================
Deadlock-free in-process request deduplicator.

Problem it solves
-----------------
Duplicate concurrent submissions (network retries, double-clicks) can waste
quota and create duplicated conversation turns.

Design (per validation report)
-------------------------------
- The lock is held only long enough to look up / insert the shared Task.
  It is RELEASED before any await, preventing the deadlock in the original
  proposal (where an existing future was awaited while holding the lock).
- asyncio.shield() protects the shared Task from cancellation by one caller
  without preventing other callers from receiving the result.
- The canonical deduplication key is a SHA-256 hash of all request-identifying
  fields: user_id, conversation_id, message, model, system_prompt, and an
  optional media digest.  (Full 64-char hex — no truncation.)
- Cleanup uses a separate lock acquisition after completion so no caller is
  ever blocked by the cleanup step.

Usage::

    dedup = RequestDeduplicator()

    async def handle(user_id, message, bot):
        return await dedup.submit(
            user_id=user_id,
            conversation_id=bot.conversation_id,
            message=message,
            model=bot.model.model_name,
            fn=lambda: bot.ask(message),
        )
"""
from __future__ import annotations

import asyncio
import hashlib
from typing import Any, Awaitable, Callable, Dict, Optional


def _make_key(
    user_id: str,
    conversation_id: str,
    message: str,
    model: str = "",
    system_prompt: str = "",
    media_digest: str = "",
) -> str:
    """
    Build a canonical SHA-256 deduplication key.

    Parameters
    ----------
    user_id : str
    conversation_id : str
    message : str
    model : str
    system_prompt : str
    media_digest : str
        A pre-computed hex digest of any attached media bytes, or empty string.

    Returns
    -------
    str
        64-character lowercase hex SHA-256 digest.
    """
    parts = "\x00".join([
        user_id,
        conversation_id,
        message,
        model,
        system_prompt,
        media_digest,
    ])
    return hashlib.sha256(parts.encode("utf-8")).hexdigest()


class RequestDeduplicator:
    """
    Coalesces identical concurrent requests so only one is sent to Gemini.

    All callers that arrive with the same key while the first request is
    in-flight will share its result without sending additional requests.

    Thread / async safety
    ---------------------
    Designed for use within a single asyncio event loop.  Not safe to share
    across multiple loops or threads without external synchronisation.
    """

    def __init__(self) -> None:
        self._in_flight: Dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()

    async def submit(
        self,
        user_id: str,
        conversation_id: str,
        message: str,
        fn: Callable[[], Awaitable[Any]],
        model: str = "",
        system_prompt: str = "",
        media_digest: str = "",
    ) -> Any:
        """
        Submit a request, coalescing duplicates.

        Parameters
        ----------
        user_id, conversation_id, message, model, system_prompt, media_digest
            Fields used to build the deduplication key.
        fn : async callable
            The actual request coroutine factory (called with no arguments).

        Returns
        -------
        Any
            The result of fn() — shared with any concurrent duplicates.
        """
        key = _make_key(user_id, conversation_id, message, model, system_prompt, media_digest)

        # ── Step 1: acquire lock, look up or create the task, release lock ───
        async with self._lock:
            if key in self._in_flight:
                existing_task = self._in_flight[key]
            else:
                existing_task = None
                # Create and schedule the real task; store it before releasing lock
                new_task = asyncio.ensure_future(fn())
                self._in_flight[key] = new_task

        # ── Step 2: lock is released — await without holding it ───────────────
        if existing_task is not None:
            # Wait for the already-running task.
            # shield() prevents our cancellation from cancelling the shared task.
            return await asyncio.shield(existing_task)

        # We own the new_task — await it and clean up on completion.
        try:
            result = await asyncio.shield(new_task)
            return result
        except asyncio.CancelledError:
            # Our await was cancelled — don't cancel the underlying task
            # (other waiters may be shielded onto it).
            raise
        except Exception:
            raise
        finally:
            # ── Step 3: remove from in-flight map after completion ─────────
            async with self._lock:
                self._in_flight.pop(key, None)

    def pending_count(self) -> int:
        """Number of in-flight deduplicated requests."""
        return len(self._in_flight)
