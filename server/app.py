"""The API behind the competition site.

Public:   leaderboard, showdown clock, rules metadata.
Gated:    submitting a bot — Google OAuth, ``@smail.iitm.ac.in`` only.
Admin:    tuning the showdown, running one on demand, bans, audit log.

Locally this also serves the static site so ``python -m server`` is the whole
stack in one command. In production nginx serves the files and proxies ``/api``
here (see ``deploy/nginx.conf``).
"""

from __future__ import annotations

import asyncio
import hashlib
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from harness.validate import ROLL_RE, parse_filename, validate
from sandbox.runner import SandboxLimits, detect_isolation

from . import config, events, security, store
from .scheduler import scheduler

REPO_ROOT = config.REPO_ROOT
WEB_DIR = REPO_ROOT / "web"
PUBLIC_DIR = REPO_ROOT / "public"

# --- lifecycle -----------------------------------------------------------------


@asynccontextmanager
async def lifespan(_app: FastAPI):
    config.ensure_dirs()
    store.connect()
    await scheduler.start()
    yield
    await scheduler.stop()


app = FastAPI(
    title="Quant Guild — Trading Bot Recruitment",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)


@app.middleware("http")
async def _security_headers(request: Request, call_next):
    response = await call_next(request)
    for header, value in security.SECURITY_HEADERS.items():
        response.headers.setdefault(header, value)
    if not request.url.path.startswith("/api/"):
        response.headers.setdefault("Content-Security-Policy", security.CONTENT_SECURITY_POLICY)
    return response


# --- identity ------------------------------------------------------------------


def current_user(request: Request) -> dict | None:
    return store.session_user(request.cookies.get(config.COOKIE_NAME, ""))


def require_user(request: Request) -> dict:
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Sign in with your smail account first.")
    if user.get("banned"):
        raise HTTPException(status_code=403, detail="This account is blocked from submitting.")
    return user


def require_admin(request: Request) -> dict:
    user = require_user(request)
    if not config.is_admin(user["email"]):
        raise HTTPException(status_code=403, detail="Admins only.")
    return user


def roll_from_email(email: str) -> str:
    """IIT Madras smail local parts are roll numbers — bind the two together."""
    local = email.split("@", 1)[0].upper()
    return local if ROLL_RE.match(local) else ""


# --- auth ----------------------------------------------------------------------


@app.get("/api/auth/login")
def auth_login(request: Request):
    if not config.oauth_configured():
        raise HTTPException(status_code=503, detail="Google sign-in is not configured yet.")
    security.rate_limit(request, "login", limit=20, window=60)

    state = secrets.token_urlsafe(24)
    url = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={config.GOOGLE_CLIENT_ID}"
        f"&redirect_uri={config.OAUTH_REDIRECT_URI}"
        "&response_type=code"
        "&scope=openid%20email%20profile"
        f"&hd={config.ALLOWED_DOMAIN}"
        f"&state={state}"
        "&prompt=select_account"
    )
    response = RedirectResponse(url, status_code=302)
    response.set_cookie(
        "qg_oauth_state", state, max_age=600, httponly=True,
        secure=config.COOKIE_SECURE, samesite="lax", path="/",
    )
    return response


@app.get("/api/auth/callback")
async def auth_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    if error:
        return RedirectResponse(f"/login?auth=failed&reason={error}", status_code=302)

    expected = request.cookies.get("qg_oauth_state", "")
    if not expected or not state or not security.constant_time_equals(state, expected):
        return RedirectResponse("/login?auth=failed&reason=state", status_code=302)
    if not code:
        return RedirectResponse("/login?auth=failed&reason=nocode", status_code=302)

    async with httpx.AsyncClient(timeout=15) as client:
        token_res = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": config.GOOGLE_CLIENT_ID,
                "client_secret": config.GOOGLE_CLIENT_SECRET,
                "redirect_uri": config.OAUTH_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        access_token = token_res.json().get("access_token")
        if not access_token:
            return RedirectResponse("/login?auth=failed&reason=token", status_code=302)

        user_res = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    profile = user_res.json()
    email = (profile.get("email") or "").lower()
    name = profile.get("name") or email.split("@")[0]

    if not profile.get("verified_email", True):
        return RedirectResponse("/login?auth=denied&reason=unverified", status_code=302)
    if not email.endswith(f"@{config.ALLOWED_DOMAIN}"):
        return RedirectResponse("/login?auth=denied&reason=domain", status_code=302)

    store.upsert_user(email, name, roll_from_email(email))
    token, _ = store.create_session(email)
    store.audit(email, "login")

    response = RedirectResponse("/submit", status_code=302)
    response.set_cookie(
        config.COOKIE_NAME, token, max_age=config.SESSION_TTL_SECONDS, httponly=True,
        secure=config.COOKIE_SECURE, samesite="lax", path="/",
    )
    response.delete_cookie("qg_oauth_state", path="/")
    return response


@app.post("/api/auth/logout")
def auth_logout(request: Request):
    security.require_same_origin(request)
    token = request.cookies.get(config.COOKIE_NAME, "")
    if token:
        store.destroy_session(token)
    response = JSONResponse({"ok": True})
    response.delete_cookie(config.COOKIE_NAME, path="/")
    return response


@app.get("/api/me")
def api_me(request: Request):
    user = current_user(request)
    if not user:
        return {"signed_in": False, "oauth_configured": config.oauth_configured()}
    return {
        "signed_in": True,
        "email": user["email"],
        "name": user["name"],
        "roll": user["roll"] or roll_from_email(user["email"]),
        "banned": bool(user["banned"]),
        "is_admin": config.is_admin(user["email"]),
        "submissions": store.submissions_for(user["roll"] or roll_from_email(user["email"])),
    }


# --- public data ---------------------------------------------------------------


@app.get("/api/state")
def api_state():
    settings = store.public_settings()
    latest = store.latest_showdown()
    return {
        "now": time.time(),
        "schedule": scheduler.state(),
        "submissions_open": bool(settings.get("submissions_open", True)),
        "variations": settings.get("variations", [1, 2, 3]),
        "num_rounds": settings.get("num_rounds", 2000),
        "group_size": settings.get("group_size", 20),
        "repeats": settings.get("repeats", 3),
        "max_bid": settings.get("max_bid", 100.0),
        "starting_capitals": settings.get("starting_capitals", [100.0]),
        "announcement": settings.get("announcement", ""),
        "deadline_iso": settings.get("deadline_iso", ""),
        "counts": store.submission_counts(),
        "last_showdown": {
            "id": latest["id"], "finished_at": latest["finished_at"], "games": latest["games"],
        } if latest else None,
    }


@app.get("/api/leaderboard")
def api_leaderboard():
    return {"rows": store.leaderboard(), "state": scheduler.state()}


@app.get("/api/leaderboard/stream")
async def api_leaderboard_stream(request: Request):
    queue = events.subscribe()

    async def generator():
        try:
            yield f"event: leaderboard\ndata: {JSONResponse(store.leaderboard()).body.decode()}\n\n"
            while True:
                if await request.is_disconnected():
                    return
                try:
                    yield await asyncio.wait_for(queue.get(), timeout=20.0)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"   # keeps proxies from dropping the stream
        finally:
            events.unsubscribe(queue)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


# --- submitting ----------------------------------------------------------------


@app.post("/api/submit")
async def api_submit(
    request: Request,
    file: UploadFile = File(...),
    user: dict = Depends(require_user),
):
    security.require_same_origin(request)
    security.rate_limit(request, "submit", limit=6, window=60)

    settings = store.get_settings()
    if not settings.get("submissions_open", True):
        raise HTTPException(status_code=403, detail="Submissions are closed.")

    expected_roll = user["roll"] or roll_from_email(user["email"])

    if expected_roll and expected_roll.upper() in {
        r.upper() for r in settings.get("banned_rolls", [])
    }:
        raise HTTPException(status_code=403, detail="This roll number is blocked from submitting.")

    cooldown = int(settings.get("submit_cooldown", config.SUBMIT_COOLDOWN_SECONDS))
    if expected_roll:
        elapsed = time.time() - store.last_submission_time(expected_roll)
        if elapsed < cooldown:
            raise HTTPException(
                status_code=429,
                detail=f"Please wait {int(cooldown - elapsed)}s before submitting again.",
            )

    filename = Path(file.filename or "").name
    if not filename.endswith(".py"):
        raise HTTPException(status_code=400, detail="Only .py files are accepted.")

    contents = await file.read(config.MAX_UPLOAD_BYTES + 1)
    if len(contents) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File is larger than {config.MAX_UPLOAD_BYTES // 1024} KB.",
        )
    if not contents:
        raise HTTPException(status_code=400, detail="That file is empty.")

    try:
        source = contents.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded Python.")

    parsed = parse_filename(filename)
    if parsed is None:
        raise HTTPException(
            status_code=400,
            detail="Name your file ROLLNO_<variation>.py — for example ME24B152_1.py",
        )
    roll, variation = parsed

    tmp_dir = config.DATA_DIR / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / f"{secrets.token_hex(8)}.py"
    tmp_path.write_text(source, encoding="utf-8")

    try:
        limits = SandboxLimits(
            round_timeout=float(settings.get("round_timeout", 1.0)),
            mem_mb=int(settings.get("mem_mb", 512)),
        )
        result = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: validate(
                filename, source, tmp_path,
                expected_roll=expected_roll,
                block_bounds=settings.get("block_bounds"),
                max_bid=float(settings.get("max_bid", 100.0)),
                starting_capital=float(settings.get("starting_capitals", [100.0])[0]),
                limits=limits,
            ),
        )

        digest = hashlib.sha256(contents).hexdigest()

        if not result.ok:
            store.record_submission(
                roll=roll, variation=variation, email=user["email"], name=user["name"],
                filename=filename, path="", sha256=digest, size=len(contents),
                status="rejected", message=result.reason, smoke_profit=0.0,
            )
            return JSONResponse({"ok": False, "message": result.reason}, status_code=400)

        final_path = config.SUBMISSIONS_DIR / f"{roll}_{variation}.py"
        final_path.write_text(source, encoding="utf-8")
        final_path.chmod(0o444)

        store.upsert_user(user["email"], user["name"], roll)
        store.record_submission(
            roll=roll, variation=variation, email=user["email"], name=user["name"],
            filename=filename, path=str(final_path), sha256=digest, size=len(contents),
            status="accepted", message="", smoke_profit=result.net_profit,
        )
        store.audit(user["email"], "submit", f"{roll}_{variation}")
        events.publish("submission", {"roll": roll, "variation": variation})

        return {
            "ok": True,
            "roll": roll,
            "variation": variation,
            "smoke": {
                "net_profit": result.net_profit,
                "wins": result.wins,
                "errors": result.errors,
                "timeouts": result.timeouts,
            },
            "message": "Accepted. Your bot plays in the next showdown.",
        }
    finally:
        tmp_path.unlink(missing_ok=True)


# --- admin ---------------------------------------------------------------------


@app.get("/api/admin/settings")
def admin_settings(admin: dict = Depends(require_admin)):
    return {
        "settings": store.get_settings(),
        "schedule": scheduler.state(),
        "isolation": detect_isolation(),
        "counts": store.submission_counts(),
    }


@app.patch("/api/admin/settings")
async def admin_update_settings(request: Request, admin: dict = Depends(require_admin)):
    security.require_same_origin(request)
    changes = await request.json()
    if not isinstance(changes, dict):
        raise HTTPException(status_code=400, detail="Expected a JSON object.")

    settings = store.update_settings(changes)
    store.audit(admin["email"], "settings", ", ".join(sorted(changes)))

    if "interval_minutes" in changes:
        scheduler.reschedule()
    events.publish("schedule", scheduler.state())
    return {"ok": True, "settings": settings, "schedule": scheduler.state()}


@app.post("/api/admin/run-now")
async def admin_run_now(request: Request, admin: dict = Depends(require_admin)):
    security.require_same_origin(request)
    if scheduler.running:
        raise HTTPException(status_code=409, detail="A showdown is already running.")
    store.audit(admin["email"], "run-now")
    scheduler.trigger_now()
    return {"ok": True, "schedule": scheduler.state()}


@app.get("/api/admin/submissions")
def admin_submissions(admin: dict = Depends(require_admin)):
    return {"submissions": store.active_submissions(), "counts": store.submission_counts()}


@app.get("/api/admin/showdowns")
def admin_showdowns(admin: dict = Depends(require_admin)):
    return {"showdowns": store.showdown_history()}


@app.get("/api/admin/audit")
def admin_audit(admin: dict = Depends(require_admin)):
    return {"audit": store.audit_log()}


@app.post("/api/admin/ban")
async def admin_ban(request: Request, admin: dict = Depends(require_admin)):
    security.require_same_origin(request)
    body = await request.json()
    roll = str(body.get("roll", "")).upper()
    banned = bool(body.get("banned", True))
    if not roll:
        raise HTTPException(status_code=400, detail="roll is required")

    settings = store.get_settings()
    rolls = {r.upper() for r in settings.get("banned_rolls", [])}
    rolls.add(roll) if banned else rolls.discard(roll)
    store.update_settings({"banned_rolls": sorted(rolls)})
    store.audit(admin["email"], "ban" if banned else "unban", roll)
    return {"ok": True, "banned_rolls": sorted(rolls)}


# --- static site (local development) -------------------------------------------

if config.SERVE_STATIC:
    if WEB_DIR.is_dir():
        app.mount("/web", StaticFiles(directory=WEB_DIR), name="web")
    if PUBLIC_DIR.is_dir():
        app.mount("/public", StaticFiles(directory=PUBLIC_DIR), name="public")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        """Serve the single page for every non-API route.

        Deliberately an allowlist: no request path is ever turned into a file
        path, so no amount of ``../`` reaches ``secret/`` or ``server/``.
        """
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        if full_path == "favicon.ico":
            icon = WEB_DIR / "favicon.svg"
            if icon.is_file():
                return FileResponse(icon, media_type="image/svg+xml")
        return FileResponse(REPO_ROOT / "index.html", media_type="text/html")


def _uvicorn_kwargs() -> dict:
    return {"host": config.HOST, "port": config.PORT, "log_level": "info"}
