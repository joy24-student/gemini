# -*- coding: utf-8 -*-
"""
gemini_client/cookie_pool.py
=============================
Multi-Account Cookie Pool Manager for High-Scale Gemini deployments.

Manages multiple Google account cookie pairs (PSID + PSIDTS) to distribute
load across accounts, avoiding rate-limits and single-account bans.

Features:
  1. Round-Robin Dispatch: Evenly distributes requests across all healthy accounts.
  2. Per-Cookie Rate Tracking: Counts requests per cookie per minute; warns at threshold.
  3. Health Check & Auto-Blacklist: Automatically marks a cookie as burned after
     repeated auth failures (401/403) and excludes it from dispatch.
  4. JSON File Loading: Load a pool of cookie pairs from a simple JSON config file.

Usage::

    pool = CookiePool.from_file("cookies_pool.json")
    psid, psidts = pool.next()
    pool.report_failure(psid)  # after a 403

cookies_pool.json format::

    [
        {"__Secure-1PSID": "...", "__Secure-1PSIDTS": "..."},
        {"__Secure-1PSID": "...", "__Secure-1PSIDTS": "..."}
    ]
"""
from __future__ import annotations

import json
import logging
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
            logger.warning(f"Cookie ...{self.psid[-8:]} blacklisted after {self.failure_count} auth failures.")

    def mark_success(self) -> None:
        self.failure_count = 0


class CookiePool:
    """
    Thread-safe round-robin pool of Google account cookie pairs.

    Parameters
    ----------
    cookies : list of (psid, psidts) tuples
    """

    def __init__(self, cookies: Optional[List[Tuple[str, str]]] = None):
        self._slots: List[_CookieSlot] = []
        self._index = 0
        self._lock = threading.Lock()
        for psid, psidts in (cookies or []):
            self.add(psid, psidts)

    @classmethod
    def from_file(cls, path: str) -> "CookiePool":
        """Load pool from JSON file: [{"__Secure-1PSID": ..., "__Secure-1PSIDTS": ...}, ...]"""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        pairs = []
        for entry in data:
            psid = entry.get("__Secure-1PSID") or entry.get("psid", "")
            psidts = entry.get("__Secure-1PSIDTS") or entry.get("psidts", "")
            if psid:
                pairs.append((psid, psidts))
        if not pairs:
            raise ValueError(f"No valid cookie pairs found in {path}")
        instance = cls(pairs)
        logger.info(f"CookiePool loaded {len(pairs)} account(s) from {path}")
        return instance

    @classmethod
    def from_list(cls, entries: List[Dict[str, str]]) -> "CookiePool":
        """Load from a list of dicts."""
        pairs = [
            (e.get("__Secure-1PSID", ""), e.get("__Secure-1PSIDTS", ""))
            for e in entries if e.get("__Secure-1PSID")
        ]
        return cls(pairs)

    def add(self, psid: str, psidts: str) -> None:
        with self._lock:
            self._slots.append(_CookieSlot(psid=psid, psidts=psidts))

    def next(self) -> Tuple[str, str]:
        """Return next healthy (psid, psidts) pair via round-robin."""
        with self._lock:
            healthy = [s for s in self._slots if s.healthy]
            if not healthy:
                raise RuntimeError(
                    "All cookies in the pool are blacklisted. Add fresh Google account cookies."
                )
            slot = healthy[self._index % len(healthy)]
            self._index = (self._index + 1) % len(healthy)
            rpm = slot.record_request()
            if rpm >= _RATE_WARN_THRESHOLD:
                logger.warning(
                    f"Cookie ...{slot.psid[-8:]} at {rpm} req/min (threshold={_RATE_WARN_THRESHOLD}). "
                    "Consider adding more accounts."
                )
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

    def status(self) -> List[Dict]:
        with self._lock:
            return [
                {
                    "psid_tail": s.psid[-8:],
                    "healthy": s.healthy,
                    "failures": s.failure_count,
                    "rpm": len([t for t in s._request_times if t > time.monotonic() - 60]),
                }
                for s in self._slots
            ]
