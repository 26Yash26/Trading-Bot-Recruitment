"""Deployment configuration, all of it from the environment.

Nothing secret is committed and nothing secret is read from inside the web root.
On the VM these come from ``/etc/quantguild.env`` (systemd ``EnvironmentFile``),
which lives outside ``/var/www/html`` and is mode 600.

The data directory holds the SQLite database and every uploaded bot file. It
**must not** be inside the deployed repo — the VM serves that directory as
static files, so anything in it is one URL away from the public.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_list(name: str) -> list[str]:
    return [item.strip().lower() for item in _env(name).split(",") if item.strip()]


# --- where state lives ---------------------------------------------------------

DATA_DIR = Path(_env("QG_DATA_DIR") or (REPO_ROOT / ".local")).resolve()
SUBMISSIONS_DIR = DATA_DIR / "submissions"
DB_PATH = DATA_DIR / "quantguild.db"

# --- identity ------------------------------------------------------------------

GOOGLE_CLIENT_ID = _env("QG_GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = _env("QG_GOOGLE_CLIENT_SECRET")
ALLOWED_DOMAIN = _env("QG_ALLOWED_DOMAIN", "smail.iitm.ac.in")
ADMIN_EMAILS = set(_env_list("QG_ADMIN_EMAILS"))

PUBLIC_ORIGIN = _env("QG_PUBLIC_ORIGIN", "http://localhost:8000").rstrip("/")
OAUTH_REDIRECT_URI = _env("QG_OAUTH_REDIRECT_URI") or f"{PUBLIC_ORIGIN}/api/auth/callback"

SESSION_TTL_SECONDS = int(_env("QG_SESSION_TTL", "43200"))  # 12 hours
COOKIE_NAME = "qg_session"
COOKIE_SECURE = PUBLIC_ORIGIN.startswith("https://")

# --- limits --------------------------------------------------------------------

MAX_UPLOAD_BYTES = int(_env("QG_MAX_UPLOAD_BYTES", str(512 * 1024)))
SUBMIT_COOLDOWN_SECONDS = int(_env("QG_SUBMIT_COOLDOWN", "60"))

# --- serving -------------------------------------------------------------------

# In production nginx serves the static site and proxies /api here, so the app
# does not need to serve files. Locally it does, so one command runs everything.
SERVE_STATIC = _env("QG_SERVE_STATIC", "1") != "0"
HOST = _env("QG_HOST", "127.0.0.1")
PORT = int(_env("QG_PORT", "8000"))


def oauth_configured() -> bool:
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)


def is_admin(email: str) -> bool:
    return bool(email) and email.lower() in ADMIN_EMAILS


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SUBMISSIONS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        DATA_DIR.chmod(0o700)
    except OSError:
        pass
