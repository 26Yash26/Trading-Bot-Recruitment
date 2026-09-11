"""The API behind the competition site.

Public:   leaderboard, showdown clock, rules metadata.
Gated:    submitting a bot, Google OAuth, ``@smail.iitm.ac.in`` only.
Admin:    tuning the showdown, running one on demand, bans, audit log.

Locally this also serves the static site so ``python -m server`` is the whole
stack in one command. In production nginx serves the files and proxies ``/api``
here (see ``deploy/nginx.conf``).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from harness.evaluate import GROUPINGS
from harness.validate import ROLL_RE, parse_filename, validate
from sandbox.runner import SandboxLimits, detect_isolation
from src.auction.capital import CapitalDraw
from src.auction.distributions import normalise_block_bounds
from src.auction.variations import VARIATIONS

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


log = logging.getLogger("quantguild")

app = FastAPI(
    title="Quant Guild, Trading Bot Recruitment",
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
    """IIT Madras smail local parts are roll numbers, bind the two together."""
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


def public_state() -> dict:
    """Everything the site needs to draw itself, and nothing more.

    Also the payload of the ``state`` server-sent event, so a setting changed in
    the control room, which variations are in play, whether submissions are
    open, the announcement, reaches every open tab without a reload.
    """
    settings = store.public_settings()
    # The public "last showdown" is the last PUBLISHED one. A practice rehearsal
    # is invisible to participants, including its timestamp.
    published = store.published_showdowns(limit=1)
    latest = published[0] if published else None
    num_rounds = int(settings.get("num_rounds", 2000))
    block_size = max(1, int(settings.get("block_size", 500)))
    return {
        "now": time.time(),
        "schedule": scheduler.state(),
        "submissions_open": bool(settings.get("submissions_open", True)),
        "variations": settings.get("variations", [1, 2]),
        "num_rounds": num_rounds,
        "block_size": block_size,
        "num_blocks": max(1, -(-num_rounds // block_size)),
        "group_size": settings.get("group_size", 20),
        "iterations": settings.get("iterations", 3),
        "grouping": settings.get("grouping", "random"),
        # The capital draw is public: §3.1 spells the whole thing out, and only
        # the block's hidden maximum that it scales is kept back.
        "capital": CapitalDraw.from_settings(settings).as_dict(),
        "announcement": settings.get("announcement", ""),
        "deadline_iso": settings.get("deadline_iso", ""),
        "submission_form_url": settings.get("submission_form_url", ""),
        "counts": store.submission_counts(),
        "last_showdown": {
            "id": latest["id"], "finished_at": latest["finished_at"], "games": latest["games"],
            "kind": latest.get("kind", store.DEFAULT_KIND),
        } if latest else None,
        # Mock and final boards are published artefacts and stay reachable after
        # the next practice run has replaced the live one.
        "published_showdowns": store.published_showdowns(),
    }


@app.get("/api/state")
def api_state():
    return public_state()


@app.get("/api/leaderboard")
def api_leaderboard(showdown: int | None = None):
    """A published board: the newest by default, or one named by id.

    There is no rolling live board. The site shows mock rounds and the finals,
    so an id is only honoured for one of those; a practice run is a private
    rehearsal and is not addressable.
    """
    if showdown is None:
        published = store.published_showdowns(limit=1)
        return {
            "rows": store.leaderboard(kinds=store.PUBLISHED_KINDS),
            "state": scheduler.state(),
            "showdown": published[0] if published else None,
        }

    published = {int(row["id"]): row for row in store.published_showdowns(limit=200)}
    row = published.get(int(showdown))
    if row is None:
        raise HTTPException(status_code=404, detail="No published showdown with that id.")
    return {
        "rows": store.leaderboard(int(showdown)),
        "state": scheduler.state(),
        "showdown": row,
    }


@app.get("/api/showdowns")
def api_showdowns():
    """Every published (mock or final) board, newest first."""
    return {"showdowns": store.published_showdowns()}


@app.get("/api/leaderboard/stream")
async def api_leaderboard_stream(request: Request):
    queue = events.subscribe()

    async def generator():
        try:
            yield (
                "event: leaderboard\ndata: "
                + JSONResponse(store.leaderboard(kinds=store.PUBLISHED_KINDS)).body.decode()
                + "\n\n"
            )
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


# --- variations released later -------------------------------------------------

LATE_VARIATIONS_JS = Path(__file__).resolve().parent / "late_variations.js"

#: Variations whose rules are withheld from the browser until they are released.
LATE_VARIATIONS = (3, 4)


@app.get("/api/variations/late.js")
def api_late_variations():
    """The browser module describing variations 3 and 4.

    Everything about them, names, rules, the worked example, the payoff
    arithmetic behind the interactive bench, lives in this one file, which sits
    under ``server/`` rather than ``web/`` so nginx will not serve it as a static
    asset (``deploy/nginx.conf`` blocks the whole directory). It is handed out
    only once the admin has switched one of them on.

    Before that this is a 404, which is exactly what the front end expects: a
    participant reading the page source on orientation night finds a dynamic
    import that fails, and nothing else. Turning variation 3 on in the control
    room publishes a ``state`` event, and every open tab imports this within the
    second.
    """
    settings = store.get_settings()
    in_play = {int(v) for v in settings.get("variations", [])}
    if not in_play.intersection(LATE_VARIATIONS):
        raise HTTPException(status_code=404, detail="Not found")
    if not LATE_VARIATIONS_JS.is_file():
        raise HTTPException(status_code=500, detail="late_variations.js is missing")

    return FileResponse(
        LATE_VARIATIONS_JS,
        media_type="text/javascript",
        # Released mid-competition, so it must not be cached as a 404 and must
        # not be cached as content once a later variation changes.
        headers={"Cache-Control": "no-store"},
    )


DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"


@app.get("/api/docs/scoring.pdf")
def api_scoring_pdf():
    """The scoring specification, in the variant this stage of the event allows.

    `docs/scoring.tex` builds twice (`scripts/build_docs.sh`): a public PDF
    covering variations 1 and 2, and a full one covering all four. Which is
    served follows the same switch as `late.js`, before release the full
    document simply is not reachable, so the V3 and V4 payoff rules cannot be
    read out of it.

    Served from `docs/`, which nginx blocks, rather than `public/`, which it
    hands out unconditionally. A file under `public/` would be one filename guess
    away from defeating the gate entirely.
    """
    settings = store.get_settings()
    in_play = {int(v) for v in settings.get("variations", [])}
    released = bool(in_play.intersection(LATE_VARIATIONS))

    path = DOCS_DIR / ("scoring.pdf" if released else "scoring-public.pdf")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Not found")

    return FileResponse(
        path,
        media_type="application/pdf",
        filename="quant-guild-scoring.pdf",
        # The file behind this URL changes the moment a variation is released.
        headers={"Cache-Control": "no-store"},
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

    # A smail address whose local part is not a roll number, a club or staff
    # account. There is no roll to bind the upload to, so the filename check in
    # `harness.validate` would have nothing to compare against and the file
    # could claim any roll it liked. Refuse rather than skip the check.
    if not expected_roll:
        raise HTTPException(
            status_code=403,
            detail="This account has no roll number attached, so it cannot submit. "
            "Sign in with your own smail address.",
        )

    if expected_roll.upper() in {
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
            detail="Name your file ROLLNO_<variation>.py, for example ME24B152_1.py",
        )
    roll, variation = parsed

    # A variation that is not in play is not on the site either, the submit
    # form will not offer it, so a file naming one is either a stale page or a
    # hand-crafted request. Both deserve the same plain answer.
    in_play = [int(v) for v in settings.get("variations", list(VARIATIONS))]
    if variation not in in_play:
        raise HTTPException(
            status_code=400,
            detail=f"Variation {variation} is not in play. "
            f"Currently accepted: {', '.join(f'variation {v}' for v in in_play) or 'none'}.",
        )

    tmp_dir = config.DATA_DIR / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / f"{secrets.token_hex(8)}.py"
    tmp_path.write_text(source, encoding="utf-8")

    try:
        limits = SandboxLimits(
            round_timeout=float(settings.get("round_timeout", 1.0)),
            mem_mb=int(settings.get("mem_mb", 512)),
        )
        try:
            result = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: validate(
                    filename, source, tmp_path,
                    expected_roll=expected_roll,
                    bounds_mode=str(settings.get("bounds_mode", "random")),
                    block_bounds=settings.get("block_bounds"),
                    capital_draw=CapitalDraw.from_settings(settings),
                    limits=limits,
                ),
            )
        except Exception:
            # validate() rejecting a bad bot returns ValidationResult(ok=False).
            # It never raises for that. A raise here means OUR settings or code
            # are broken (this is exactly how a malformed block_bounds surfaced:
            # https://github.com/26Yash26/Trading-Bot-Recruitment, fixed in
            # harness/validate.py, but nothing should ever again be able to turn
            # a config mistake into a bare "Internal Server Error" that reads as
            # if the participant's file were at fault). Log it for us, and tell
            # them plainly that it is not their bug.
            log.exception("submission check crashed for %s", filename)
            store.record_submission(
                roll=roll, variation=variation, email=user["email"], name=user["name"],
                filename=filename, path="", sha256=hashlib.sha256(contents).hexdigest(),
                size=len(contents), status="error",
                message="Server-side check crashed", smoke_profit=0.0,
            )
            return JSONResponse(
                {
                    "ok": False,
                    "message": (
                        "The check crashed on our side, not a problem with your file. "
                        "We've logged it. Try again in a minute, and flag it on the "
                        "guild group if it keeps happening."
                    ),
                },
                status_code=500,
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
        # A resubmission for the same roll+variation reuses this path, and the
        # previous file was locked read-only below — unlock it first or the
        # write raises PermissionError, which nothing downstream catches and
        # which used to surface as a bare "Internal Server Error".
        if final_path.exists():
            final_path.chmod(0o600)
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


def normalise_variations(value: object) -> list[int]:
    """A non-empty subset of the four variations, in order.

    The switchboard in the admin console decides what the whole site shows, so
    an empty or malformed list here would leave participants with a page that
    describes no game at all. Refuse it at the door rather than storing it.
    """
    if not isinstance(value, list):
        raise HTTPException(status_code=400, detail="variations must be a list.")
    # `bool` is an `int` in Python and `True` would quietly become variation 1.
    if any(not isinstance(item, int) or isinstance(item, bool) for item in value):
        raise HTTPException(status_code=400, detail="variations must be whole numbers.")
    chosen = sorted(set(value))
    if not chosen or any(item not in VARIATIONS for item in chosen):
        raise HTTPException(
            status_code=400,
            detail="Pick at least one variation, out of 1, 2, 3 and 4.",
        )
    return chosen


def normalise_grouping_setting(value: object) -> str | list[str]:
    """One grouping mode, or one per iteration (§9).

    A single string keeps the old behaviour, that mode for every iteration. A
    list plays the real tournament in one run: `["random", "random", "balanced"]`
    is qualification, and a list shorter than `iterations` holds its last entry.
    """
    if isinstance(value, str):
        if value not in GROUPINGS:
            raise HTTPException(
                status_code=400,
                detail=f"grouping must be one of {', '.join(GROUPINGS)}.",
            )
        return value
    if isinstance(value, list) and value:
        bad = [m for m in value if not isinstance(m, str) or m not in GROUPINGS]
        if bad:
            raise HTTPException(
                status_code=400,
                detail=f"grouping list may only contain {', '.join(GROUPINGS)}.",
            )
        return list(value)
    raise HTTPException(
        status_code=400,
        detail="grouping must be a mode, or a non-empty list of modes.",
    )


@app.patch("/api/admin/settings")
async def admin_update_settings(request: Request, admin: dict = Depends(require_admin)):
    security.require_same_origin(request)
    changes = await request.json()
    if not isinstance(changes, dict):
        raise HTTPException(status_code=400, detail="Expected a JSON object.")

    if "variations" in changes:
        changes["variations"] = normalise_variations(changes["variations"])

    if "grouping" in changes:
        changes["grouping"] = normalise_grouping_setting(changes["grouping"])

    if "bounds_mode" in changes:
        if changes["bounds_mode"] not in ("random", "fixed"):
            raise HTTPException(
                status_code=400, detail="bounds_mode must be 'random' or 'fixed'."
            )

    # The hidden bounds are the one setting that can break every game at once:
    # M_b divides the normalised profit and scales the capital draw, so a zero,
    # a negative or an inverted pair takes the whole showdown down. It is typed
    # by hand into the console minutes before a run, so check it at the door.
    if "block_bounds" in changes:
        try:
            changes["block_bounds"] = [
                [list(pair) for pair in schedule]
                for schedule in normalise_block_bounds(changes["block_bounds"])
            ]
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None

    settings = store.update_settings(changes)
    store.audit(admin["email"], "settings", ", ".join(sorted(changes)))

    if "interval_minutes" in changes:
        scheduler.reschedule()
    events.publish("schedule", scheduler.state())
    events.publish("state", public_state())
    return {"ok": True, "settings": settings, "schedule": scheduler.state()}


@app.post("/api/admin/run-now")
async def admin_run_now(request: Request, admin: dict = Depends(require_admin)):
    """Start a showdown now, labelled `practice` (default), `mock` or `final`.

    The label decides three things: whether the board survives the next practice
    run, whether it appears in the public archive, and, because a balanced or
    finals iteration seeds on the standing so far, which previous board this run
    is seeded from. Getting it wrong is not cosmetic, so it is audited.
    """
    security.require_same_origin(request)
    if scheduler.running:
        raise HTTPException(status_code=409, detail="A showdown is already running.")

    try:
        body = await request.json()
    except Exception:  # noqa: BLE001 - an empty body is the ordinary case
        body = {}
    requested = str((body or {}).get("kind", store.DEFAULT_KIND))
    if requested not in store.SHOWDOWN_KINDS:
        raise HTTPException(
            status_code=400,
            detail=f"kind must be one of {', '.join(store.SHOWDOWN_KINDS)}.",
        )

    # Which variations this run covers. Omitted means every released one, which
    # is what the clock does. Naming a subset is how a single variation gets
    # replayed without disturbing the others: the live board takes each
    # variation from the newest run that scored it, so the rest stay put.
    settings = store.get_settings()
    released = [int(v) for v in settings.get("variations", [])]
    raw = (body or {}).get("variations")
    chosen: list[int] | None = None
    if raw is not None:
        if not isinstance(raw, list) or not raw:
            raise HTTPException(
                status_code=400, detail="variations must be a non-empty list."
            )
        try:
            chosen = sorted({int(v) for v in raw})
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=400, detail="variations must be whole numbers."
            ) from None
        unreleased = [v for v in chosen if v not in released]
        if unreleased:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Cannot run variation "
                    + ", ".join(str(v) for v in unreleased)
                    + ": it is not released. Turn it on first."
                ),
            )

    covers = chosen or released
    store.audit(
        admin["email"], "run-now",
        f"kind={requested} variations={','.join(str(v) for v in covers)}",
    )
    scheduler.trigger_now(requested, tuple(chosen) if chosen else None)
    return {
        "ok": True,
        "kind": requested,
        "variations": covers,
        "schedule": scheduler.state(),
    }


@app.get("/api/admin/submissions")
def admin_submissions(admin: dict = Depends(require_admin)):
    return {"submissions": store.active_submissions(), "counts": store.submission_counts()}


@app.get("/api/admin/showdowns")
def admin_showdowns(admin: dict = Depends(require_admin)):
    return {
        "showdowns": store.showdown_history(),
        "kinds": list(store.SHOWDOWN_KINDS),
    }


@app.delete("/api/admin/showdowns/{showdown_id}")
async def admin_delete_showdown(
    showdown_id: int, request: Request, admin: dict = Depends(require_admin)
):
    """Delete a showdown and every result it holds.

    Published boards are what the site shows, so removing one changes what
    participants see: the board before it becomes current again, and it becomes
    the standing that the next run of that kind seeds its balanced iterations
    on. A running showdown cannot be deleted, because its rows are still being
    written.
    """
    security.require_same_origin(request)
    if scheduler.running and scheduler.current_id == int(showdown_id):
        raise HTTPException(
            status_code=409,
            detail="That showdown is still running. Wait for it to finish.",
        )

    removed = store.delete_showdown(int(showdown_id))
    if removed is None:
        raise HTTPException(status_code=404, detail="No showdown with that id.")

    store.audit(
        admin["email"], "delete-showdown",
        f"id={showdown_id} kind={removed.get('kind')} games={removed.get('games')}",
    )
    events.publish("leaderboard", store.leaderboard(kinds=store.PUBLISHED_KINDS))
    events.publish("state", public_state())
    return {"ok": True, "deleted": removed}


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
