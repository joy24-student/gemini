# -*- coding: utf-8 -*-
"""
gemini_client/cookie_pool.py
=============================
Multi-Account Cookie Pool Manager for High-Scale Gemini deployments.

Manages multiple Google account cookie pairs (PSID + PSIDTS) to distribute
load across accounts, avoiding rate-limits and single-account bans.

Features:
  1. Named Account Labels: Assign human-readable account names (e.g. "Joy Primary", "Work Account").
  2. Multi-Format Loading: Load from env var JSON string, numbered env vars, or cookies_pool.json file.
  3. Round-Robin Dispatch: Evenly distributes requests across all healthy accounts.
  4. Per-Cookie Rate Tracking: Counts requests per cookie per minute; warns at threshold.
  5. Health Check & Auto-Blacklist: Automatically marks a cookie as burned after
     repeated auth failures (401/403) and excludes it from dispatch.
  6. Safe Account Summary API: Exposes account names and health status WITHOUT leaking secret cookie strings.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_RATE_WARN_THRESHOLD = 25
_MAX_FAILURES = 3


@dataclass
class _CookieSlot:
    id: str
    name: str
    psid: str
    psidts: str
    healthy: bool = True
    failure_count: int = 0
    _request_times: List[float] = field(default_factory=list)

    def record_request(self) -> int:
        now = time.monotonic()
        cutoff = now - 60.0
        self._request_times = [t for t in self._request_times if t > cutoff]
        self._request_times.append(now)
        return len(self._request_times)

    def mark_failure(self) -> None:
        self.failure_count += 1
        if self.failure_count >= _MAX_FAILURES:
            self.healthy = False
            logger.warning(f"Account '{self.name}' (...{self.psid[-8:]}) blacklisted after {self.failure_count} auth failures.")

    def mark_success(self) -> None:
        self.failure_count = 0


class CookiePool:
    """
    Thread-safe pool of named Google account cookie pairs.
    """

    def __init__(self, entries: Optional[List[Dict[str, str]]] = None):
        self._slots: List[_CookieSlot] = []
        self._index = 0
        self._active_id: Optional[str] = None
        self._lock = threading.Lock()
        for e in (entries or []):
            self.add(
                psid=e.get("__Secure-1PSID") or e.get("psid", ""),
                psidts=e.get("__Secure-1PSIDTS") or e.get("psidts", ""),
                name=e.get("name") or e.get("label", ""),
            )

    @classmethod
    def from_env(cls) -> "CookiePool":
        """
        Automatically build CookiePool from environment variables.
        Tries:
          1. GEMINI_COOKIES_JSON environment variable (JSON string of account objects)
          2. GEMINI_COOKIE_POOL_PATH environment variable (File path)
          3. Numbered env vars (GEMINI_COOKIE_1_PSID, GEMINI_COOKIE_1_PSIDTS, etc.)
          4. Single-account env vars (GEMINI_1PSID, GEMINI_1PSIDTS)
        """
        entries = []

        # 1. GEMINI_COOKIES_JSON
        raw_json = os.environ.get("GEMINI_COOKIES_JSON", "").strip()
        if raw_json:
            try:
                parsed = json.loads(raw_json)
                if isinstance(parsed, list):
                    entries.extend(parsed)
            except Exception as e:
                logger.error(f"Failed to parse GEMINI_COOKIES_JSON: {e}")

        # 2. GEMINI_COOKIE_POOL_PATH
        pool_path = os.environ.get("GEMINI_COOKIE_POOL_PATH", "").strip()
        if pool_path and os.path.exists(pool_path):
            try:
                parsed = json.loads(Path(pool_path).read_text(encoding="utf-8"))
                if isinstance(parsed, list):
                    entries.extend(parsed)
            except Exception as e:
                logger.error(f"Failed to load GEMINI_COOKIE_POOL_PATH ({pool_path}): {e}")

        # 3. Numbered env vars: GEMINI_COOKIE_1_PSID, GEMINI_COOKIE_2_PSID...
        for idx in range(1, 20):
            psid = os.environ.get(f"GEMINI_COOKIE_{idx}_PSID", "").strip()
            psidts = os.environ.get(f"GEMINI_COOKIE_{idx}_PSIDTS", "").strip()
            name = os.environ.get(f"GEMINI_COOKIE_{idx}_NAME", f"Account {idx}").strip()
            if psid:
                entries.append({"name": name, "__Secure-1PSID": psid, "__Secure-1PSIDTS": psidts})

        # 4. Single account fallback: GEMINI_1PSID, GEMINI_1PSIDTS
        if not entries:
            psid = os.environ.get("GEMINI_1PSID", "").strip()
            psidts = os.environ.get("GEMINI_1PSIDTS", "").strip()
            if psid:
                entries.append({"name": "Primary Account", "__Secure-1PSID": psid, "__Secure-1PSIDTS": psidts})

        return cls.from_list(entries)

    @classmethod
    def from_file(cls, path: str) -> "CookiePool":
        """Load pool from JSON file: [{"name": "...", "__Secure-1PSID": ..., "__Secure-1PSIDTS": ...}, ...]"""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError(f"Cookie pool file {path} must contain a JSON array.")
        return cls.from_list(data)

    @classmethod
    def from_list(cls, entries: List[Dict[str, str]]) -> "CookiePool":
        """Load from a list of dict objects."""
        pool = cls()
        for idx, e in enumerate(entries, 1):
            psid = e.get("__Secure-1PSID") or e.get("psid", "")
            psidts = e.get("__Secure-1PSIDTS") or e.get("psidts", "")
            name = e.get("name") or e.get("label") or f"Account {idx}"
            if psid:
                pool.add(psid, psidts, name=name)
        return pool

    def add(self, psid: str, psidts: str, name: Optional[str] = None) -> str:
        """Add a cookie pair to the pool with a human-readable name."""
        with self._lock:
            slot_id = f"acc_{len(self._slots) + 1}"
            account_name = name or f"Account {len(self._slots) + 1}"
            slot = _CookieSlot(id=slot_id, name=account_name, psid=psid, psidts=psidts)
            self._slots.append(slot)
            if self._active_id is None:
                self._active_id = slot_id
            return slot_id

    def set_active_account(self, slot_id_or_name: str) -> bool:
        """Set a specific account to be active for subsequent requests."""
        with self._lock:
            for s in self._slots:
                if s.id == slot_id_or_name or s.name == slot_id_or_name:
                    self._active_id = s.id
                    logger.info(f"Switched active cookie account to '{s.name}' ({s.id})")
                    return True
            return False

    def next(self) -> Tuple[str, str]:
        """Return next healthy (psid, psidts) pair."""
        with self._lock:
            healthy = [s for s in self._slots if s.healthy]
            if not healthy:
                raise RuntimeError("All cookie accounts in the pool are blacklisted. Please refresh session cookies.")

            # If user explicitly selected an active account and it's healthy, use it
            if self._active_id:
                for s in healthy:
                    if s.id == self._active_id:
                        s.record_request()
                        return s.psid, s.psidts

            # Round-robin dispatch
            slot = healthy[self._index % len(healthy)]
            self._index = (self._index + 1) % len(healthy)
            rpm = slot.record_request()
            if rpm >= _RATE_WARN_THRESHOLD:
                logger.warning(f"Account '{slot.name}' at {rpm} req/min (threshold={_RATE_WARN_THRESHOLD}).")
            return slot.psid, slot.psidts

    def report_failure(self, psid: str) -> None:
        with self._lock:
            for slot in self._slots:
                if slot.psid == psid:
                    slot.mark_failure()
                    break

    def report_success(self, psid: str) -> None:
        with self._lock:
            for slot in self._slots:
                if slot.psid == psid:
                    slot.mark_success()
                    break

    @property
    def healthy_count(self) -> int:
        with self._lock:
            return sum(1 for s in self._slots if s.healthy)

    @property
    def total_count(self) -> int:
        with self._lock:
            return len(self._slots)

    def safe_account_summaries(self) -> List[Dict[str, str | bool | int]]:
        """Return account summaries WITHOUT exposing sensitive cookie values."""
        with self._lock:
            now = time.monotonic()
            return [
                {
                    "id": s.id,
                    "name": s.name,
                    "active": (s.id == self._active_id),
                    "healthy": s.healthy,
                    "failures": s.failure_count,
                    "rpm": len([t for t in s._request_times if t > now - 60]),
                }
                for s in self._slots
            ]
