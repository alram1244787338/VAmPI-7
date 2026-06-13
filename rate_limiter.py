"""
Lightweight, reusable in-memory rate limiter for Flask/Connexion endpoints.

Uses a sliding window counter approach keyed by client IP.
Configurable via environment variables:
    RATE_LIMIT_MAX_REQUESTS   – max requests allowed per window (default: 10)
    RATE_LIMIT_WINDOW_SECONDS – window size in seconds (default: 60)
    RATE_LIMIT_ENABLED        – set to "0" to disable rate limiting entirely (default: 1)
"""

import time
import threading
import os
from functools import wraps
from flask import request, Response
import json


# ---------------------------------------------------------------------------
# Configuration (read once at import time, overridable per-instance)
# ---------------------------------------------------------------------------
DEFAULT_MAX_REQUESTS = int(os.getenv('RATE_LIMIT_MAX_REQUESTS', 10))
DEFAULT_WINDOW_SECONDS = int(os.getenv('RATE_LIMIT_WINDOW_SECONDS', 60))
RATE_LIMIT_ENABLED = int(os.getenv('RATE_LIMIT_ENABLED', 1))


class RateLimiter:
    """
    A simple sliding-window rate limiter keyed by client IP.

    Usage::

        limiter = RateLimiter(max_requests=5, window_seconds=30)

        @limiter.limit
        def my_view():
            ...
    """

    def __init__(self, max_requests=None, window_seconds=None):
        self.max_requests = max_requests if max_requests is not None else DEFAULT_MAX_REQUESTS
        self.window_seconds = window_seconds if window_seconds is not None else DEFAULT_WINDOW_SECONDS
        # _hits: { ip: [timestamp, timestamp, ...] }
        self._hits = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Core check
    # ------------------------------------------------------------------
    def is_rate_limited(self, key):
        """Return True if *key* has exceeded the limit within the current window."""
        now = time.time()
        window_start = now - self.window_seconds

        with self._lock:
            timestamps = self._hits.get(key, [])
            # Prune old entries
            timestamps = [ts for ts in timestamps if ts > window_start]
            if len(timestamps) >= self.max_requests:
                self._hits[key] = timestamps
                return True
            timestamps.append(now)
            self._hits[key] = timestamps
            return False

    # ------------------------------------------------------------------
    # Decorator for Flask / Connexion view functions
    # ------------------------------------------------------------------
    def limit(self, func):
        """Decorator that rate-limits a Flask/Connexion view function."""
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not RATE_LIMIT_ENABLED:
                return func(*args, **kwargs)

            client_ip = request.remote_addr or '127.0.0.1'
            if self.is_rate_limited(client_ip):
                body = json.dumps({
                    "status": "fail",
                    "message": "Rate limit exceeded. Please try again later."
                })
                return Response(body, 429, mimetype="application/json")
            return func(*args, **kwargs)
        return wrapper

    # ------------------------------------------------------------------
    # Introspection helpers (used by /health endpoint)
    # ------------------------------------------------------------------
    def get_config(self):
        return {
            "max_requests": self.max_requests,
            "window_seconds": self.window_seconds,
            "enabled": bool(RATE_LIMIT_ENABLED),
        }

    def get_stats(self):
        """Return a snapshot of current tracked IPs and their hit counts."""
        now = time.time()
        with self._lock:
            stats = {}
            for ip, timestamps in self._hits.items():
                active = [ts for ts in timestamps if ts > now - self.window_seconds]
                if active:
                    stats[ip] = len(active)
            return stats

    def reset(self):
        with self._lock:
            self._hits.clear()


# ---------------------------------------------------------------------------
# Pre-built limiter instances with different profiles
# ---------------------------------------------------------------------------

# Strict limiter for auth endpoints (login, register) – lower thresholds
auth_limiter = RateLimiter(
    max_requests=int(os.getenv('RATE_LIMIT_AUTH_MAX_REQUESTS', 5)),
    window_seconds=int(os.getenv('RATE_LIMIT_AUTH_WINDOW_SECONDS', 60)),
)

# General limiter for read endpoints (list users, get by username, book detail)
read_limiter = RateLimiter(
    max_requests=int(os.getenv('RATE_LIMIT_READ_MAX_REQUESTS', 20)),
    window_seconds=int(os.getenv('RATE_LIMIT_READ_WINDOW_SECONDS', 60)),
)

# Registry of all limiter instances – used by /health to report config
ALL_LIMITERS = {
    "auth": auth_limiter,
    "read": read_limiter,
}
