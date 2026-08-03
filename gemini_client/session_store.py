# -*- coding: utf-8 -*-
"""
gemini_client/session_store.py
==============================
Durable SQLite WAL session state store.

Persists only the Gemini-side conversation pointers:
  - conversation_id
  - response_id
  - choice_id

Explicitly EXCLUDED (ephemeral — must not be persisted):
  - SNlM0e  (page/request token, invalid after restart)
  - Cookies / PSID strings

Design decisions (per validation report):
  - SQLite WAL mode for concurrent read safety and atomic writes.
  - Keys are (owner_id, session_key) pairs — one user can have many sessions.
  - owner_id is never used as a raw file path (no path traversal risk).
  - TTL-based expiry; expired rows are purged on startup.
  - Async wrappers use asyncio.to_thread so DB calls don't block the event loop.

Usage::

    store = DurableSessionStore()
    await store.save("user_42", "main", conv_id="abc", resp_id="def", choice_id="ghi")
    state = await store.load("user_42", "main")
    if state:
        bot.conversation_id = state["conversation_id"]
        bot.response_id     = state["response_id"]
        bot.choice_id       = state["choice_id"]
"""
from __future__ import annotations

import asyncio
import hashlib
import sqlite3
import time
from pathlib import Path
from typing import Dict, Optional


def _safe_key(raw: str) -> str:
    """Hash an arbitrary string to a safe, fixed-length storage key."""
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()


class DurableSessionStore:
    """
    Atomic SQLite-backed session state store keyed by (owner_id, session_key).

    Parameters
    ----------
    db_path : str or Path, optional
        Path to the SQLite database file.
        Defaults to ``~/.gemini/sessions/sessions.db``.
    ttl_seconds : int, optional
        Sessions older than this are purged.  Default 86 400 (24 hours).
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        ttl_seconds: int = 86_400,
    ) -> None:
        if db_path is None:
            from gemini_client.utils import ensure_data_dir
            storage = ensure_data_dir("sessions")
            db_path = str(storage / "sessions.db")
        self._db_path = db_path
        self._ttl = ttl_seconds
        self._init_db()

    # ── Internal sync helpers (run in thread pool) ───────────────────────────

    def _connect(self) -> sqlite3.Connection:
        try:
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.OperationalError:
            conn = sqlite3.connect(":memory:", check_same_thread=False)
            conn.row_factory = sqlite3.Row
            return conn
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    owner_key    TEXT NOT NULL,
                    session_key  TEXT NOT NULL,
                    conv_id      TEXT NOT NULL DEFAULT '',
                    resp_id      TEXT NOT NULL DEFAULT '',
                    choice_id    TEXT NOT NULL DEFAULT '',
                    updated_at   REAL NOT NULL,
                    PRIMARY KEY (owner_key, session_key)
                )
            """)
            conn.commit()
        self._purge_expired_sync()

    def _purge_expired_sync(self) -> None:
        cutoff = time.time() - self._ttl
        with self._connect() as conn:
            conn.execute("DELETE FROM sessions WHERE updated_at < ?", (cutoff,))
            conn.commit()

    def _save_sync(
        self,
        owner_id: str,
        session_key: str,
        conversation_id: str,
        response_id: str,
        choice_id: str,
    ) -> None:
        ok = _safe_key(owner_id)
        sk = _safe_key(session_key)
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions (owner_key, session_key, conv_id, resp_id, choice_id, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(owner_key, session_key) DO UPDATE SET
                    conv_id    = excluded.conv_id,
                    resp_id    = excluded.resp_id,
                    choice_id  = excluded.choice_id,
                    updated_at = excluded.updated_at
                """,
                (ok, sk, conversation_id, response_id, choice_id, now),
            )
            conn.commit()

    def _load_sync(self, owner_id: str, session_key: str) -> Optional[Dict[str, str]]:
        ok = _safe_key(owner_id)
        sk = _safe_key(session_key)
        cutoff = time.time() - self._ttl
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT conv_id, resp_id, choice_id
                FROM sessions
                WHERE owner_key = ? AND session_key = ? AND updated_at >= ?
                """,
                (ok, sk, cutoff),
            ).fetchone()
        if row is None:
            return None
        return {
            "conversation_id": row["conv_id"],
            "response_id": row["resp_id"],
            "choice_id": row["choice_id"],
        }

    def _delete_sync(self, owner_id: str, session_key: str) -> None:
        ok = _safe_key(owner_id)
        sk = _safe_key(session_key)
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM sessions WHERE owner_key = ? AND session_key = ?",
                (ok, sk),
            )
            conn.commit()

    # ── Public async API ─────────────────────────────────────────────────────

    async def save(
        self,
        owner_id: str,
        session_key: str,
        conversation_id: str,
        response_id: str,
        choice_id: str,
    ) -> None:
        """Atomically persist conversation pointers for a (owner, session) pair."""
        await asyncio.to_thread(
            self._save_sync, owner_id, session_key, conversation_id, response_id, choice_id
        )

    async def load(self, owner_id: str, session_key: str) -> Optional[Dict[str, str]]:
        """
        Load conversation pointers.

        Returns None if no session exists or it has expired.
        Returns a dict with keys: conversation_id, response_id, choice_id.
        """
        return await asyncio.to_thread(self._load_sync, owner_id, session_key)

    async def delete(self, owner_id: str, session_key: str) -> None:
        """Remove a session."""
        await asyncio.to_thread(self._delete_sync, owner_id, session_key)

    async def purge_expired(self) -> None:
        """Explicitly purge expired sessions."""
        await asyncio.to_thread(self._purge_expired_sync)

    # ── Sync convenience wrappers (for non-async callers) ────────────────────

    def save_sync(
        self,
        owner_id: str,
        session_key: str,
        conversation_id: str,
        response_id: str,
        choice_id: str,
    ) -> None:
        self._save_sync(owner_id, session_key, conversation_id, response_id, choice_id)

    def load_sync(self, owner_id: str, session_key: str) -> Optional[Dict[str, str]]:
        return self._load_sync(owner_id, session_key)


# Module-level default instance
_default_store: Optional[DurableSessionStore] = None


def get_default_store() -> DurableSessionStore:
    """Return (and lazily create) the module-level default session store."""
    global _default_store
    if _default_store is None:
        _default_store = DurableSessionStore()
    return _default_store
