# -*- coding: utf-8 -*-
"""
gemini_client/observability.py
==============================
Prometheus metrics and health endpoints for the Gemini server.

Design decisions (per validation report)
-----------------------------------------
- All metric update methods are PUBLIC (no private field access like _value.get()).
- Labels use LOW CARDINALITY only: 'model', 'status' ('ok'/'error'), 'method'.
  Never: user_id, cookie_id, conversation_id, prompt text, exception strings.
- Separate /health/live and /health/ready endpoints:
    /health/live  — process is running (liveness probe: never checks Gemini)
    /health/ready — service can accept traffic (readiness probe: checks cookie pool)
- /metrics returns Prometheus text format.
- Credential health is reported as COUNTS ONLY (healthy_count / total_count).
  No cookie values, tail strings, or PSID fragments are exposed.
- Supports a custom Prometheus registry for unit tests.

Usage (FastAPI integration)::

    from gemini_client.observability import Metrics, add_health_routes

    metrics = Metrics()
    add_health_routes(app, metrics, cookie_pool=pool)

    # Record a request:
    metrics.record_request(model="gemini-2.5-flash", status="ok", latency=0.42)
    metrics.set_active_sessions(12)
    metrics.set_cookie_pool(healthy=3, total=5)
"""
from __future__ import annotations

import time
from typing import Any, Callable, Optional

try:
    from prometheus_client import (  # type: ignore
        CollectorRegistry,
        Counter,
        Gauge,
        Histogram,
        CONTENT_TYPE_LATEST,
        generate_latest,
    )
    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False


# ── Metrics container ─────────────────────────────────────────────────────────
class Metrics:
    """
    Manages Prometheus counters, gauges, and histograms for the Gemini server.

    Parameters
    ----------
    registry : CollectorRegistry, optional
        Custom registry (useful for tests).  Defaults to a new registry.
    """

    def __init__(self, registry: Any = None) -> None:
        self._available = _PROMETHEUS_AVAILABLE
        if not self._available:
            return

        self._registry = registry or CollectorRegistry()

        self._request_total = Counter(
            "gemini_requests_total",
            "Total Gemini API requests",
            ["model", "status"],
            registry=self._registry,
        )
        self._request_latency = Histogram(
            "gemini_request_duration_seconds",
            "Gemini API request duration in seconds",
            ["model"],
            buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
            registry=self._registry,
        )
        self._active_sessions = Gauge(
            "gemini_active_sessions",
            "Number of active user sessions",
            registry=self._registry,
        )
        self._cookie_pool_healthy = Gauge(
            "gemini_cookie_pool_healthy_total",
            "Number of healthy cookies in the pool",
            registry=self._registry,
        )
        self._cookie_pool_total = Gauge(
            "gemini_cookie_pool_total",
            "Total number of cookies in the pool",
            registry=self._registry,
        )
        self._stream_chunks = Counter(
            "gemini_stream_chunks_total",
            "Total streaming text chunks yielded",
            ["model"],
            registry=self._registry,
        )

    # ── Public update methods ─────────────────────────────────────────────────

    def record_request(
        self,
        model: str,
        status: str,          # "ok" | "error"
        latency: float,       # seconds
    ) -> None:
        """Record a completed request (success or failure)."""
        if not self._available:
            return
        safe_model = model[:64] if model else "unknown"
        safe_status = status if status in ("ok", "error") else "error"
        self._request_total.labels(model=safe_model, status=safe_status).inc()
        self._request_latency.labels(model=safe_model).observe(latency)

    def record_stream_chunk(self, model: str) -> None:
        """Record one streamed chunk."""
        if not self._available:
            return
        self._stream_chunks.labels(model=model[:64] if model else "unknown").inc()

    def set_active_sessions(self, count: int) -> None:
        """Update the active session gauge."""
        if not self._available:
            return
        self._active_sessions.set(count)

    def set_cookie_pool(self, healthy: int, total: int) -> None:
        """Update cookie pool health gauges (counts only, no identifiers)."""
        if not self._available:
            return
        self._cookie_pool_healthy.set(healthy)
        self._cookie_pool_total.set(total)

    def export(self) -> bytes:
        """Return Prometheus text format bytes."""
        if not self._available:
            return b"# prometheus_client not installed\n"
        return generate_latest(self._registry)

    @property
    def content_type(self) -> str:
        if not self._available:
            return "text/plain"
        return CONTENT_TYPE_LATEST


# ── FastAPI route registration ────────────────────────────────────────────────
def add_health_routes(
    app: Any,
    metrics: Metrics,
    cookie_pool: Any = None,
    ready_check: Optional[Callable[[], bool]] = None,
) -> None:
    """
    Register /health/live, /health/ready, and /metrics on a FastAPI app.

    Parameters
    ----------
    app : FastAPI
    metrics : Metrics
    cookie_pool : CookiePool, optional
        Used to check whether any healthy cookies are available for readiness.
    ready_check : callable, optional
        Additional callable returning bool for the readiness check.
    """
    try:
        from fastapi.responses import JSONResponse, Response
    except ImportError:
        return

    @app.get("/health/live", tags=["Health"])
    async def health_live() -> JSONResponse:
        """
        Liveness probe.
        Returns 200 as long as the process is running.
        Does NOT check external dependencies.
        """
        return JSONResponse({"status": "alive", "timestamp": time.time()})

    @app.get("/health/ready", tags=["Health"])
    async def health_ready() -> JSONResponse:
        """
        Readiness probe.
        Returns 200 only when the service can accept Gemini traffic:
          - At least one healthy cookie in the pool (if a pool is provided).
          - Any additional ready_check() passes.
        """
        issues = []

        if cookie_pool is not None:
            try:
                healthy = cookie_pool.healthy_count
                total = cookie_pool.total_count
                metrics.set_cookie_pool(healthy=healthy, total=total)
                if healthy == 0:
                    issues.append("no_healthy_cookies")
            except Exception:
                issues.append("cookie_pool_error")

        if ready_check is not None:
            try:
                if not ready_check():
                    issues.append("custom_check_failed")
            except Exception:
                issues.append("custom_check_error")

        if issues:
            return JSONResponse(
                {"status": "not_ready", "issues": issues, "timestamp": time.time()},
                status_code=503,
            )
        return JSONResponse({"status": "ready", "timestamp": time.time()})

    @app.get("/metrics", tags=["Observability"])
    async def prometheus_metrics() -> Response:
        """Prometheus metrics endpoint."""
        return Response(
            content=metrics.export(),
            media_type=metrics.content_type,
        )
