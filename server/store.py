"""SQLite persistence: users, sessions, submissions, showdowns, settings, audit.

One small database, WAL mode, guarded by a lock — the write volume here is a few
hundred submissions and a leaderboard every two hours, so anything bigger would
be furniture. It lives in ``config.DATA_DIR``, deliberately outside the web root.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from . import config

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    email      TEXT PRIMARY KEY,
    name       TEXT NOT NULL DEFAULT '',
    roll       TEXT NOT NULL DEFAULT '',
    banned     INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    last_seen  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token      TEXT PRIMARY KEY,
    email      TEXT NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_expiry ON sessions(expires_at);

CREATE TABLE IF NOT EXISTS submissions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    roll       TEXT NOT NULL,
    variation  INTEGER NOT NULL,
    email      TEXT NOT NULL,
    name       TEXT NOT NULL DEFAULT '',
    filename   TEXT NOT NULL,
    path       TEXT NOT NULL,
    sha256     TEXT NOT NULL,
    size       INTEGER NOT NULL,
    status     TEXT NOT NULL,
    message    TEXT NOT NULL DEFAULT '',
    smoke_profit REAL NOT NULL DEFAULT 0,
    active     INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sub_active ON submissions(active, variation);
CREATE INDEX IF NOT EXISTS idx_sub_roll ON submissions(roll, variation);

CREATE TABLE IF NOT EXISTS showdowns (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  REAL NOT NULL,
    finished_at REAL,
    games       INTEGER NOT NULL DEFAULT 0,
    status      TEXT NOT NULL,
    error       TEXT NOT NULL DEFAULT '',
    settings    TEXT NOT NULL DEFAULT '{}',
    -- What this run was for. See `SHOWDOWN_KINDS`.
    kind        TEXT NOT NULL DEFAULT 'practice'
);
CREATE INDEX IF NOT EXISTS idx_showdowns_kind ON showdowns(kind, status, finished_at);

CREATE TABLE IF NOT EXISTS results (
    showdown_id INTEGER NOT NULL,
    key         TEXT NOT NULL,
    variation   INTEGER NOT NULL,
    payload     TEXT NOT NULL,
    PRIMARY KEY (showdown_id, key, variation)
);

CREATE TABLE IF NOT EXISTS audit (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    at     REAL NOT NULL,
    actor  TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT ''
);
"""

#: What a showdown was run for. The distinction is not cosmetic:
#:
#: ``practice``  the 2-hourly clock. Rewritten constantly, graded never.
#: ``mock``      an announced mock auction. Its board is a published artefact and
#:               must survive the next practice run.
#: ``final``     the run after the deadline. The result.
#:
#: A ``balanced`` or ``finals`` iteration seeds on the standing so far, so it
#: matters enormously which board that comes from. Seeding reads the latest
#: finished run **of the same kind** — before this column existed it read
#: whatever had finished last, which on a two-hourly clock is a practice run.
SHOWDOWN_KINDS = ("practice", "mock", "final")
DEFAULT_KIND = "practice"


def normalise_kind(value: object) -> str:
    """A run kind, or ``DEFAULT_KIND`` for anything unrecognised."""
    text = str(value or "").strip().lower()
    return text if text in SHOWDOWN_KINDS else DEFAULT_KIND


# Everything the admin page can change. Kept here so a new deployment and an
# upgraded one agree on defaults.
DEFAULT_SETTINGS: dict[str, Any] = {
    "submissions_open": True,
    "showdown_enabled": True,
    "interval_minutes": 120,
    # Variations 3 and 4 are released after mock auction 1 (problem statement §2),
    # so they start switched off and the admin turns them on when the time comes.
    "variations": [1, 2],
    # The game (§3).
    "num_rounds": 2000,
    "block_size": 500,
    "group_size": 20,
    # The tournament (§9): how many iterations, and how groups are drawn.
    "iterations": 3,
    # One mode for every iteration, or one per iteration (§9). A list shorter
    # than `iterations` holds its last entry, so the default below means
    # "iteration 1 draws blind, and every iteration after it is seeded on the
    # standing so far" — the tournament, run in full, on every showdown.
    "grouping": ["random", "balanced"],   # random | balanced | finals
    "finals_size": 20,
    # The capital draw at every block boundary (§3.1):
    #   C = m_b + (M_b - m_b) * kappa,  kappa ~ U[kappa_lo, kappa_hi]
    "kappa_lo": 0.5,
    "kappa_hi": 2.5,
    # How each iteration's hidden bounds are chosen. "random" draws m_b and the
    # range off the published grids from `seed`; "fixed" uses `block_bounds`
    # below verbatim, for reproducing one specific run.
    "bounds_mode": "random",
    # Only consulted when `bounds_mode` is "fixed". Never leaves the server.
    # Either one schedule of four blocks (reused by every iteration) or one
    # schedule per iteration — see
    # `src.auction.distributions.normalise_block_bounds`.
    #
    # These differ in BOTH scale and width on purpose. Identical blocks would
    # mean there is no regime change to detect, which switches off the whole
    # point of the block structure.
    "block_bounds": [
        [[0.0, 100.0], [40.0, 60.0], [0.0, 400.0], [5.0, 25.0]],
        [[10.0, 30.0], [0.0, 250.0], [60.0, 90.0], [0.0, 50.0]],
        [[0.0, 75.0], [100.0, 500.0], [20.0, 40.0], [0.0, 150.0]],
    ],
    "seed": 20260916,
    # Sandbox and throughput.
    "workers": 4,
    "round_timeout": 1.0,
    "mem_mb": 512,
    "submit_cooldown": 60,
    "banned_rolls": [],
    # Site copy.
    "announcement": "",
    "deadline_iso": "2026-09-16T23:59:00+05:30",
    "submission_form_url": "",
    # Runtime clock state, persisted so the countdown survives a redeploy.
    "next_run_at": 0.0,
    "last_run_at": 0.0,
}

# Never leaves the server: the hidden distribution the bots are being tested on.
SECRET_SETTING_KEYS = {"block_bounds", "seed"}


def connect() -> sqlite3.Connection:
    global _conn
    with _lock:
        if _conn is None:
            config.ensure_dirs()
            _conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
            _conn.row_factory = sqlite3.Row
            _conn.execute("PRAGMA journal_mode=WAL")
            _conn.execute("PRAGMA foreign_keys=ON")
            _conn.executescript(SCHEMA)
            _migrate(_conn)
            _conn.commit()
            try:
                Path(config.DB_PATH).chmod(0o600)
            except OSError:
                pass
        return _conn


#: Columns added after the first deployment. ``CREATE TABLE IF NOT EXISTS`` is a
#: no-op on a database that already has the table, so a new column never reaches
#: the VM without this — and the VM's database is the one holding every real
#: submission, so it is never dropped and recreated.
MIGRATIONS: tuple[tuple[str, str, str], ...] = (
    ("showdowns", "kind", "TEXT NOT NULL DEFAULT 'practice'"),
)


def _migrate(conn: sqlite3.Connection) -> None:
    """Add any column in ``MIGRATIONS`` the database does not already have."""
    for table, column, decl in MIGRATIONS:
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        if not existing:
            continue                       # table not created yet; SCHEMA owns it
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def _exec(sql: str, params: tuple = ()) -> sqlite3.Cursor:
    with _lock:
        conn = connect()
        cur = conn.execute(sql, params)
        conn.commit()
        return cur


def _query(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    with _lock:
        return connect().execute(sql, params).fetchall()


# --- settings ------------------------------------------------------------------


def get_settings() -> dict[str, Any]:
    """Defaults, overlaid with what has been saved.

    Keys that are no longer in ``DEFAULT_SETTINGS`` are dropped rather than
    passed through: a database written by an older build still holds settings the
    problem statement has since retired, and they must not reach the site.
    """
    stored = {row["key"]: json.loads(row["value"]) for row in _query("SELECT key, value FROM settings")}
    known = {k: v for k, v in stored.items() if k in DEFAULT_SETTINGS}
    return {**DEFAULT_SETTINGS, **known}


def public_settings() -> dict[str, Any]:
    """Settings safe to hand to a browser — the hidden bounds and seed stay here."""
    return {k: v for k, v in get_settings().items() if k not in SECRET_SETTING_KEYS}


def update_settings(changes: dict[str, Any]) -> dict[str, Any]:
    with _lock:
        conn = connect()
        for key, value in changes.items():
            if key not in DEFAULT_SETTINGS:
                continue
            conn.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(value)),
            )
        conn.commit()
    return get_settings()


# --- users and sessions --------------------------------------------------------


def upsert_user(email: str, name: str, roll: str = "") -> dict:
    now = time.time()
    _exec(
        "INSERT INTO users(email, name, roll, created_at, last_seen) VALUES(?,?,?,?,?) "
        "ON CONFLICT(email) DO UPDATE SET name=excluded.name, last_seen=excluded.last_seen, "
        "roll=CASE WHEN excluded.roll != '' THEN excluded.roll ELSE users.roll END",
        (email.lower(), name, roll.upper(), now, now),
    )
    return get_user(email) or {}


def get_user(email: str) -> dict | None:
    rows = _query("SELECT * FROM users WHERE email = ?", (email.lower(),))
    return dict(rows[0]) if rows else None


def set_user_banned(email: str, banned: bool) -> None:
    _exec("UPDATE users SET banned = ? WHERE email = ?", (1 if banned else 0, email.lower()))


def create_session(email: str) -> tuple[str, float]:
    token = secrets.token_urlsafe(32)
    now = time.time()
    expires = now + config.SESSION_TTL_SECONDS
    _exec(
        "INSERT INTO sessions(token, email, created_at, expires_at) VALUES(?,?,?,?)",
        (token, email.lower(), now, expires),
    )
    _exec("DELETE FROM sessions WHERE expires_at < ?", (now,))
    return token, expires


def session_user(token: str) -> dict | None:
    if not token:
        return None
    rows = _query(
        "SELECT u.* FROM sessions s JOIN users u ON u.email = s.email "
        "WHERE s.token = ? AND s.expires_at > ?",
        (token, time.time()),
    )
    return dict(rows[0]) if rows else None


def destroy_session(token: str) -> None:
    _exec("DELETE FROM sessions WHERE token = ?", (token,))


# --- submissions ---------------------------------------------------------------


def record_submission(
    *, roll: str, variation: int, email: str, name: str, filename: str,
    path: str, sha256: str, size: int, status: str, message: str, smoke_profit: float,
) -> int:
    with _lock:
        conn = connect()
        if status == "accepted":
            conn.execute(
                "UPDATE submissions SET active = 0 WHERE roll = ? AND variation = ?",
                (roll, variation),
            )
        cur = conn.execute(
            "INSERT INTO submissions(roll, variation, email, name, filename, path, sha256, "
            "size, status, message, smoke_profit, active, created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (roll, variation, email.lower(), name, filename, path, sha256, size,
             status, message, smoke_profit, 1 if status == "accepted" else 0, time.time()),
        )
        conn.commit()
        return int(cur.lastrowid)


def active_submissions(variation: int | None = None) -> list[dict]:
    """The latest accepted file per (roll, variation) — what a showdown plays."""
    if variation is None:
        rows = _query("SELECT * FROM submissions WHERE active = 1 ORDER BY roll")
    else:
        rows = _query(
            "SELECT * FROM submissions WHERE active = 1 AND variation = ? ORDER BY roll",
            (variation,),
        )
    return [dict(r) for r in rows]


def submissions_for(roll: str) -> list[dict]:
    rows = _query(
        "SELECT * FROM submissions WHERE roll = ? ORDER BY created_at DESC LIMIT 50",
        (roll.upper(),),
    )
    return [dict(r) for r in rows]


def last_submission_time(roll: str) -> float:
    rows = _query("SELECT MAX(created_at) AS t FROM submissions WHERE roll = ?", (roll.upper(),))
    return float(rows[0]["t"] or 0.0)


def submission_counts() -> dict:
    rows = _query(
        "SELECT variation, COUNT(*) AS n FROM submissions WHERE active = 1 GROUP BY variation"
    )
    per = {int(r["variation"]): int(r["n"]) for r in rows}
    unique = _query("SELECT COUNT(DISTINCT roll) AS n FROM submissions WHERE active = 1")
    return {"per_variation": per, "participants": int(unique[0]["n"] or 0)}


# --- showdowns and results -----------------------------------------------------


def start_showdown(settings: dict, kind: str = DEFAULT_KIND) -> int:
    cur = _exec(
        "INSERT INTO showdowns(started_at, status, settings, kind) VALUES(?,?,?,?)",
        (time.time(), "running", json.dumps({k: v for k, v in settings.items()
                                             if k not in SECRET_SETTING_KEYS}),
         normalise_kind(kind)),
    )
    return int(cur.lastrowid)


def finish_showdown(showdown_id: int, *, games: int, rows: list[dict], error: str = "") -> None:
    with _lock:
        conn = connect()
        for row in rows:
            conn.execute(
                "INSERT INTO results(showdown_id, key, variation, payload) VALUES(?,?,?,?) "
                "ON CONFLICT(showdown_id, key, variation) DO UPDATE SET payload=excluded.payload",
                (showdown_id, row["key"], row["variation"], json.dumps(row)),
            )
        conn.execute(
            "UPDATE showdowns SET finished_at=?, games=?, status=?, error=? WHERE id=?",
            (time.time(), games, "error" if error else "done", error, showdown_id),
        )
        conn.commit()


def latest_showdown(status: str = "done", kind: str | None = None) -> dict | None:
    """The most recent finished run, optionally restricted to one kind.

    ``kind=None`` means "whatever ran last", which is what the live board wants:
    a practice run is still the freshest picture of the field. Seeding wants the
    opposite and always passes a kind.
    """
    if kind is None:
        rows = _query(
            "SELECT * FROM showdowns WHERE status = ? ORDER BY finished_at DESC LIMIT 1",
            (status,),
        )
    else:
        rows = _query(
            "SELECT * FROM showdowns WHERE status = ? AND kind = ? "
            "ORDER BY finished_at DESC LIMIT 1",
            (status, normalise_kind(kind)),
        )
    return dict(rows[0]) if rows else None


def showdown_history(limit: int = 20, kind: str | None = None) -> list[dict]:
    if kind is None:
        rows = _query("SELECT * FROM showdowns ORDER BY started_at DESC LIMIT ?", (limit,))
    else:
        rows = _query(
            "SELECT * FROM showdowns WHERE kind = ? ORDER BY started_at DESC LIMIT ?",
            (normalise_kind(kind), limit),
        )
    return [dict(r) for r in rows]


def published_showdowns(limit: int = 30) -> list[dict]:
    """Finished mock and final runs, newest first — the archive the site offers.

    Practice runs are excluded on purpose. There have been hundreds of them, they
    are rewritten every two hours, and none of them means anything; an archive
    that lists them buries the two boards that do.
    """
    rows = _query(
        "SELECT id, started_at, finished_at, games, kind FROM showdowns "
        "WHERE status = 'done' AND kind IN ('mock', 'final') "
        "ORDER BY finished_at DESC LIMIT ?",
        (limit,),
    )
    return [dict(r) for r in rows]


def leaderboard(showdown_id: int | None = None, kind: str | None = None) -> list[dict]:
    """Ranked rows from a showdown, joined to the display name of each roll.

    With no ``showdown_id`` this is the latest finished run — of ``kind``, if one
    is given. Naming an id wins over naming a kind.
    """
    if showdown_id is None:
        latest = latest_showdown(kind=kind)
        if latest is None:
            return []
        showdown_id = int(latest["id"])

    rows = _query("SELECT payload FROM results WHERE showdown_id = ?", (showdown_id,))
    names = {
        r["roll"]: r["name"]
        for r in _query("SELECT roll, name FROM submissions WHERE active = 1")
    }
    out = []
    for row in rows:
        payload = json.loads(row["payload"])
        payload["name"] = names.get(payload["key"], "")
        out.append(payload)
    out.sort(key=lambda r: (r["variation"], r.get("rank") or 9999))
    return out


# --- audit ---------------------------------------------------------------------


def audit(actor: str, action: str, detail: str = "") -> None:
    _exec(
        "INSERT INTO audit(at, actor, action, detail) VALUES(?,?,?,?)",
        (time.time(), actor, action, detail[:1000]),
    )


def audit_log(limit: int = 100) -> list[dict]:
    return [dict(r) for r in _query("SELECT * FROM audit ORDER BY at DESC LIMIT ?", (limit,))]
