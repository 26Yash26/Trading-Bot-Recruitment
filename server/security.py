"""Request-level defences: rate limiting and same-origin checks.

Small and dependency-free on purpose — one process, one deployment, a few
hundred users. ``slowapi`` would add a dependency to do the same job.
"""

from __future__ import annotations

import hmac
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from . import config

_lock = threading.Lock()
_hits: dict[tuple[str, str], deque] = defaultdict(deque)

# A key is one (client, bucket) pair. Sweeping keeps a client that rotates its
# apparent address from growing this dict without bound.
_MAX_IDLE_SECONDS = 3600.0
_SWEEP_EVERY_SECONDS = 300.0
_last_sweep = 0.0


def client_ip(request: Request) -> str:
    """Real client address, trusting only the proxy hop nginx adds.

    ``X-Real-IP`` is the one to believe: nginx sets it from ``$remote_addr``
    with ``proxy_set_header``, which *replaces* anything the client sent.

    ``X-Forwarded-For`` is not, because nginx builds it with
    ``$proxy_add_x_forwarded_for`` — it *appends* the peer address to whatever
    arrived. So its leftmost entry is whatever the client made up, and only the
    rightmost entry is the hop nginx actually observed. Reading the left of it
    would let anyone mint a fresh rate-limit bucket per request.
    """
    real = request.headers.get("x-real-ip", "").strip()
    if real:
        return real
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def _sweep_locked(now: float) -> None:
    """Drop buckets nobody has touched lately. Caller holds ``_lock``."""
    global _last_sweep
    if now - _last_sweep < _SWEEP_EVERY_SECONDS:
        return
    _last_sweep = now
    stale = [k for k, hits in _hits.items() if not hits or now - hits[-1] > _MAX_IDLE_SECONDS]
    for key in stale:
        del _hits[key]


def rate_limit(request: Request, bucket: str, limit: int, window: float) -> None:
    """Allow ``limit`` requests per ``window`` seconds per IP per bucket."""
    key = (client_ip(request), bucket)
    now = time.monotonic()
    with _lock:
        _sweep_locked(now)
        hits = _hits[key]
        while hits and now - hits[0] > window:
            hits.popleft()
        if len(hits) >= limit:
            retry = int(window - (now - hits[0])) + 1
            raise HTTPException(
                status_code=429,
                detail=f"Too many requests. Try again in {retry}s.",
                headers={"Retry-After": str(retry)},
            )
        hits.append(now)


def require_same_origin(request: Request) -> None:
    """Reject cross-site state changes.

    The session cookie is already ``SameSite=Lax``, which stops a cross-site form
    POST from carrying it. This is the second lock on the same door, and it also
    covers the case where a future change loosens the cookie policy.
    """
    origin = request.headers.get("origin") or ""
    if not origin:
        # Same-origin form posts and non-browser clients omit Origin; the cookie
        # policy is what protects those.
        return
    allowed = {config.PUBLIC_ORIGIN, "http://localhost:8000", "http://127.0.0.1:8000"}
    if origin.rstrip("/") not in {a.rstrip("/") for a in allowed}:
        raise HTTPException(status_code=403, detail="Cross-origin request rejected")


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=(), payment=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}

# The site loads its own CSS/JS plus Google Fonts; nothing else, and no inline
# script (the frontend keeps all JS in files precisely so this can stay strict).
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "object-src 'none'"
)
