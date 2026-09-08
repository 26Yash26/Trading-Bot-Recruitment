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


def client_ip(request: Request) -> str:
    """Real client address, trusting only the proxy hop nginx adds."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(request: Request, bucket: str, limit: int, window: float) -> None:
    """Allow ``limit`` requests per ``window`` seconds per IP per bucket."""
    key = (client_ip(request), bucket)
    now = time.monotonic()
    with _lock:
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
