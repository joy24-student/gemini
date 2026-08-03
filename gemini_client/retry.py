# -*- coding: utf-8 -*-
"""
gemini_client/retry.py
======================
Bounded retry engine with full jitter and Retry-After support.

Design decisions (per validation report):
  - Small bounded budget (default 3 attempts) to avoid worsening throttling.
  - Full jitter: sleep = random(0, min(cap, base * 2^attempt)).
  - Respects Retry-After header when present.
  - Does NOT retry on authentication failures (401, 403) or CAPTCHA redirects.
  - Does NOT retry when the response is a google.com/sorry CAPTCHA page.
  - Raises TerminalError for non-retriable failures so callers can handle them
    without inspecting error strings.

Usage::

    from gemini_client.retry import with_retry, TerminalError, RetryConfig

    cfg = RetryConfig(max_attempts=3, base_delay=1.0, cap=30.0)

    async def my_request():
        ...

    result = await with_retry(my_request, cfg)
"""
from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional, Set, TypeVar

T = TypeVar("T")

# HTTP status codes that must NOT be retried
_TERMINAL_STATUSES: Set[int] = {401, 403, 404, 405, 410}

# URLs that indicate a CAPTCHA or auth challenge — abort immediately
_CAPTCHA_MARKERS = (
    "google.com/sorry",
    "accounts.google.com/ServiceLogin",
    "accounts.google.com/signin",
)


class TerminalError(Exception):
    """
    Raised when the request failed with a non-retriable error.

    Attributes
    ----------
    status_code : int or None
        HTTP status code, if applicable.
    is_auth_failure : bool
        True for 401 / 403 responses.
    is_captcha : bool
        True when Google returned a CAPTCHA / sorry page.
    """

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        is_auth_failure: bool = False,
        is_captcha: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.is_auth_failure = is_auth_failure
        self.is_captcha = is_captcha


@dataclass
class RetryConfig:
    """Configuration for the retry engine."""
    max_attempts: int = 3
    base_delay: float = 1.0    # seconds
    cap: float = 30.0          # maximum sleep cap in seconds
    # HTTP status codes to retry (in addition to network errors)
    retryable_statuses: Set[int] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.retryable_statuses is None:
            self.retryable_statuses = {429, 500, 502, 503, 504}


def _full_jitter(attempt: int, base: float, cap: float) -> float:
    """Full jitter: sleep = random(0, min(cap, base * 2**attempt))."""
    return random.uniform(0.0, min(cap, base * (2 ** attempt)))


def _is_captcha_response(response: Any) -> bool:
    """Detect CAPTCHA / auth-challenge redirect in a response object."""
    url = ""
    try:
        url = str(response.url)
    except Exception:
        pass
    try:
        url = url or str(response.headers.get("location", ""))
    except Exception:
        pass
    return any(marker in url for marker in _CAPTCHA_MARKERS)


def _retry_after_seconds(response: Any) -> Optional[float]:
    """Parse Retry-After header value (seconds or HTTP-date)."""
    try:
        header = response.headers.get("Retry-After", "")
        if header:
            return float(header)
    except (ValueError, AttributeError):
        pass
    return None


async def with_retry(
    fn: Callable[[], Awaitable[T]],
    config: Optional[RetryConfig] = None,
    on_retry: Optional[Callable[[int, Exception], None]] = None,
) -> T:
    """
    Call an async function with bounded retry + full-jitter backoff.

    Parameters
    ----------
    fn : async callable
        The coroutine factory to call.  Called with no arguments; create a
        closure if you need to pass parameters.
    config : RetryConfig, optional
        Retry parameters.  Defaults to RetryConfig().
    on_retry : callable, optional
        Called before each retry with (attempt_number, last_exception).

    Returns
    -------
    T
        The return value of fn() on success.

    Raises
    ------
    TerminalError
        For auth failures, CAPTCHA responses, or non-retriable HTTP errors.
    Exception
        The last exception when all attempts are exhausted.
    """
    if config is None:
        config = RetryConfig()

    last_exc: Optional[Exception] = None

    for attempt in range(config.max_attempts):
        try:
            result = await fn()

            # Check for CAPTCHA in the response object itself
            if hasattr(result, "status_code") or hasattr(result, "url"):
                status = getattr(result, "status_code", None)

                if _is_captcha_response(result):
                    raise TerminalError(
                        "Google returned a CAPTCHA/auth challenge. Refresh your cookies.",
                        status_code=status,
                        is_captcha=True,
                    )

                if status in _TERMINAL_STATUSES:
                    raise TerminalError(
                        f"HTTP {status} — non-retriable error.",
                        status_code=status,
                        is_auth_failure=status in (401, 403),
                    )

                if status in config.retryable_statuses:
                    # Respect Retry-After if present
                    ra = _retry_after_seconds(result)
                    if ra is not None:
                        await asyncio.sleep(min(ra, config.cap))
                    else:
                        await asyncio.sleep(_full_jitter(attempt, config.base_delay, config.cap))
                    last_exc = Exception(f"HTTP {status}")
                    if on_retry:
                        on_retry(attempt + 1, last_exc)
                    continue

            return result  # type: ignore[return-value]

        except TerminalError:
            raise
        except (asyncio.CancelledError, KeyboardInterrupt):
            raise
        except Exception as exc:
            last_exc = exc
            # Check if this is an HTTP error with a terminal status
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in _TERMINAL_STATUSES:
                raise TerminalError(
                    f"HTTP {status}: {exc}",
                    status_code=status,
                    is_auth_failure=status in (401, 403),
                ) from exc
            if status and _is_captcha_response(getattr(exc, "response", exc)):
                raise TerminalError(
                    "CAPTCHA/auth challenge detected.",
                    status_code=status,
                    is_captcha=True,
                ) from exc

            if attempt < config.max_attempts - 1:
                delay = _full_jitter(attempt, config.base_delay, config.cap)
                if on_retry:
                    on_retry(attempt + 1, exc)
                await asyncio.sleep(delay)

    # All attempts exhausted
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Retry loop exited without result or exception.")
