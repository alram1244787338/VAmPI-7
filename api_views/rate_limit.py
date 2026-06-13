"""
Lightweight, dependency-free rate limiting for VAmPI.

VAmPI's README lists "Lack of Resources & Rate Limiting" as one of its
weaknesses. This module adds a small, reusable throttle that can be hung on any
Connexion operation with a single decorator, so login / register / lookup style
endpoints stop being trivially floodable.

Design choices:
  * In-memory sliding-window log keyed by (bucket, client-ip). No Redis, no
    extra pip dependency -- it stays "lightweight" and is plenty for a single
    process demo / teaching API. (Each worker process keeps its own counters,
    so behind several gunicorn workers the effective limit is per-worker.)
  * Everything is tunable through environment variables so local demos and
    load tests can dial the thresholds up/down without touching code.
  * When a caller is throttled we answer with the exact same error envelope the
    rest of the API uses -- ``{"status": "fail", "message": "..."}`` -- plus a
    standard ``Retry-After`` header, so existing clients keep parsing responses
    the same way.
"""

import math
import os
import threading
import time
from collections import defaultdict, deque
from functools import wraps

from flask import Response, request


def _env_int(name, default):
    """Read an int env var, falling back to ``default`` on missing/garbage."""
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_bool(name, default):
    """Read a boolean-ish env var (1/true/yes/on)."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ('1', 'true', 'yes', 'on')


# --- global configuration (read once at import) ------------------------------

# Master on/off switch -- flip RATELIMIT_ENABLED=0 to disable throttling
# entirely (handy while running a load test against the vulnerable behaviour).
ENABLED = _env_bool('RATELIMIT_ENABLED', True)

# Fallback limit applied to any bucket without its own override.
DEFAULT_LIMIT = _env_int('RATELIMIT_DEFAULT_LIMIT', 50)
DEFAULT_WINDOW = _env_int('RATELIMIT_DEFAULT_WINDOW', 60)

# Built-in per-profile defaults (limit, window-seconds) for the buckets we wire
# up out of the box. They are still fully overridable via RATELIMIT_<PROFILE>_*
# env vars; any bucket not listed here falls back to the global default above.
#   auth      -> login / register: strict, to blunt credential stuffing
#   sensitive -> per-object lookups (user-by-name, book-by-title)
#   browse    -> listing endpoints
_PROFILE_DEFAULTS = {
    'auth': (5, 60),
    'sensitive': (20, 60),
    'browse': (40, 60),
}

# Buckets that have actually been registered via the decorator, mapped to their
# resolved (limit, window). Populated at import time as endpoints are wired up,
# and surfaced through get_config_snapshot() for the /health endpoint.
_registered = {}

# Per-key history of request timestamps (monotonic seconds).
_hits = defaultdict(deque)
_lock = threading.Lock()


def _resolve(bucket, limit, window):
    """
    Resolve and remember the effective (limit, window) for a bucket.

    Precedence: explicit decorator args > per-bucket env vars
    (RATELIMIT_<BUCKET>_LIMIT / _WINDOW) > global defaults. Resolving a brand
    new bucket name therefore gives it an env knob for free, which keeps adding
    throttling to future endpoints a one-liner.
    """
    key = bucket.upper().replace('-', '_')
    base_limit, base_window = _PROFILE_DEFAULTS.get(bucket, (DEFAULT_LIMIT, DEFAULT_WINDOW))
    eff_limit = limit if limit is not None else _env_int('RATELIMIT_%s_LIMIT' % key, base_limit)
    eff_window = window if window is not None else _env_int('RATELIMIT_%s_WINDOW' % key, base_window)
    _registered[bucket] = {'limit': eff_limit, 'window': eff_window}
    return eff_limit, eff_window


def _client_ip():
    """Best-effort client identifier, honouring X-Forwarded-For if present."""
    forwarded = request.headers.get('X-Forwarded-For')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.remote_addr or 'unknown'


def _check(scope, limit, window):
    """
    Register a hit for ``scope`` and decide whether it is allowed.

    Returns (allowed, remaining, retry_after_seconds). A non-positive limit or
    window means "unlimited" so a bucket can be effectively switched off.
    """
    if limit <= 0 or window <= 0:
        return True, -1, 0

    now = time.monotonic()
    with _lock:
        bucket = _hits[scope]
        # Drop timestamps that have aged out of the window.
        cutoff = now - window
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()

        if len(bucket) >= limit:
            retry_after = max(1, math.ceil(bucket[0] + window - now))
            return False, 0, retry_after

        bucket.append(now)
        return True, limit - len(bucket), 0


def _too_many_response(retry_after):
    """429 response in VAmPI's standard error envelope."""
    body = '{ "status": "fail", "message": "Too many requests. Please slow down and try again later."}'
    response = Response(body, 429, mimetype='application/json')
    response.headers['Retry-After'] = str(retry_after)
    return response


def rate_limit(bucket=None, limit=None, window=None):
    """
    Decorator that throttles a Connexion/Flask operation.

    Usage::

        @rate_limit('auth')                 # use the "auth" preset / env knobs
        def login_user(): ...

        @rate_limit('comments', limit=10, window=60)   # explicit override
        def add_comment(): ...

    ``bucket`` namespaces the counter (and selects env overrides); it defaults
    to the wrapped function's name. The wrapped signature is preserved with
    functools.wraps so Connexion still injects path/query parameters correctly.
    """

    def decorator(func):
        name = bucket or func.__name__
        eff_limit, eff_window = _resolve(name, limit, window)

        @wraps(func)
        def wrapper(*args, **kwargs):
            if ENABLED:
                scope = '%s:%s' % (name, _client_ip())
                allowed, _remaining, retry_after = _check(scope, eff_limit, eff_window)
                if not allowed:
                    return _too_many_response(retry_after)
            return func(*args, **kwargs)

        return wrapper

    return decorator


def get_config_snapshot():
    """Serializable view of the current configuration for the /health endpoint.

    Shape matches the OpenAPI ``rate_limiting`` schema: a global on/off switch
    plus a map of profiles -- the buckets actually wired up, plus the catch-all
    ``default`` applied to any endpoint without its own override. A profile counts
    as enabled only when throttling is globally on and its numbers are positive
    (a non-positive limit/window means "unlimited", i.e. effectively disabled).
    """
    profiles = {'default': {'limit': DEFAULT_LIMIT, 'window': DEFAULT_WINDOW}}
    profiles.update(_registered)

    def describe(cfg):
        limit, window = cfg['limit'], cfg['window']
        return {
            'max_requests': limit,
            'window_seconds': window,
            'enabled': ENABLED and limit > 0 and window > 0,
        }

    return {
        'globally_enabled': ENABLED,
        'profiles': {name: describe(cfg) for name, cfg in profiles.items()},
    }
