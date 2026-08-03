# -*- coding: utf-8 -*-
"""
gemini_client/sync_bridge.py
============================
True synchronous streaming bridge for AsyncChatbot.ask_stream().

Problem it solves
-----------------
The original Chatbot.ask_stream() collected all chunks into a list before
yielding (see core.py _collect()), making it non-streaming in practice.

Design (per validation report)
-------------------------------
- One owned event-loop thread is created per SyncStreamBridge instance.
  The AsyncChatbot and its httpx session MUST be created on that thread's loop.
- asyncio.run_coroutine_threadsafe submits work to the owned loop without
  touching the caller's (possibly absent) loop.
- A bounded queue (default maxsize=256) provides backpressure so the producer
  does not run arbitrarily far ahead of the consumer.
- Exceptions from the async generator are propagated to the caller via the
  queue sentinel mechanism.
- Consumer cancellation is handled: when the generator is abandoned (e.g.
  caller breaks out of for-loop), the producer task is cancelled.
- Clean shutdown: call bridge.shutdown() or use as a context manager.

Usage::

    bridge = SyncStreamBridge()

    # All async work must happen on bridge.loop:
    bot = bridge.run_coroutine(AsyncChatbot.create(...))

    # True streaming — yields chunks as they arrive:
    for chunk in bridge.stream(bot.ask_stream("Hello")):
        print(chunk, end="", flush=True)

    bridge.shutdown()

    # Or as a context manager:
    with SyncStreamBridge() as bridge:
        bot = bridge.run_coroutine(AsyncChatbot.create(...))
        for chunk in bridge.stream(bot.ask_stream("Hello")):
            print(chunk, end="", flush=True)
"""
from __future__ import annotations

import asyncio
import queue
import threading
from typing import Any, AsyncGenerator, Generator, Optional, TypeVar

T = TypeVar("T")
_SENTINEL = object()         # signals end-of-stream
_ERROR_SENTINEL = object()   # signals an error — payload is the exception


class SyncStreamBridge:
    """
    Owns a dedicated event-loop thread and provides sync wrappers for
    async generators and coroutines.

    Parameters
    ----------
    queue_maxsize : int
        Maximum number of items buffered between producer and consumer.
        Default 256.  Set to 0 for an unbounded queue.
    """

    def __init__(self, queue_maxsize: int = 256) -> None:
        self._queue_maxsize = queue_maxsize
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop, name="gemini-async-loop", daemon=True
        )
        self._thread.start()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        """The owned event loop.  Use this when creating async resources."""
        return self._loop

    def run_coroutine(self, coro: Any) -> Any:
        """
        Submit a coroutine to the owned loop and block until it completes.

        Parameters
        ----------
        coro : coroutine
            The coroutine to run.

        Returns
        -------
        Any
            The coroutine's return value.

        Raises
        ------
        Exception
            Any exception raised by the coroutine.
        """
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()

    def stream(self, agen: AsyncGenerator[T, None]) -> Generator[T, None, None]:
        """
        Iterate an async generator synchronously, yielding items as they arrive.

        Parameters
        ----------
        agen : AsyncGenerator
            An async generator (e.g. bot.ask_stream("…")).

        Yields
        ------
        T
            Items produced by the async generator.

        Raises
        ------
        Exception
            Any exception raised inside the async generator.
        """
        q: queue.Queue = queue.Queue(maxsize=self._queue_maxsize)
        producer_task: Optional[asyncio.Task] = None

        async def _producer() -> None:
            nonlocal producer_task
            producer_task = asyncio.current_task()
            try:
                async for item in agen:
                    q.put(item)            # blocks if queue is full (backpressure)
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                q.put((_ERROR_SENTINEL, exc))
                return
            q.put(_SENTINEL)

        asyncio.run_coroutine_threadsafe(_producer(), self._loop)

        try:
            while True:
                item = q.get()
                if item is _SENTINEL:
                    return
                if isinstance(item, tuple) and len(item) == 2 and item[0] is _ERROR_SENTINEL:
                    raise item[1]
                yield item
        except GeneratorExit:
            # Consumer abandoned the generator — cancel the async producer
            if producer_task is not None:
                self._loop.call_soon_threadsafe(producer_task.cancel)

    def shutdown(self, wait: bool = True) -> None:
        """Stop the owned event loop and join the thread."""
        self._loop.call_soon_threadsafe(self._loop.stop)
        if wait:
            self._thread.join(timeout=5.0)

    # ── Context manager ───────────────────────────────────────────────────────

    def __enter__(self) -> "SyncStreamBridge":
        return self

    def __exit__(self, *args: Any) -> None:
        self.shutdown()
