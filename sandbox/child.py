"""The process a participant's bot actually runs in (sandbox layer 2).

Started by ``sandbox.runner`` as::

    python3 -m sandbox.child <bot_file> [--mem-mb N] [--cpu-secs N] [--no-net-shim]

and then speaks newline-delimited JSON with its parent:

    parent -> child   {"op": "init", "config": {...}}   -> {"ok": true}
               {"op": "bid",  "obs": {...}}      -> {"ok": true, "bid": 1.23}
               {"op": "stop"}                    -> exits

**stdout belongs to the protocol, not to the bot.** The first thing this module
does is dup the real stdout to a private fd and point fd 1 at /dev/null, so a
participant's ``print()`` cannot corrupt or spoof a protocol frame.

Everything here is a backstop *inside* the process. The real confinement is the
namespace/container the runner starts us in, see ``sandbox/runner.py``.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import resource
import sys

# --- Layer 2a: take stdout away from the bot before anything else runs ---------

_PROTO_FD = os.dup(1)
_devnull = os.open(os.devnull, os.O_WRONLY)
os.dup2(_devnull, 1)
os.close(_devnull)
sys.stdout = open(os.devnull, "w")  # noqa: SIM115 - lives for the process


def _send(payload: dict) -> None:
    line = (json.dumps(payload) + "\n").encode("utf-8")
    written = 0
    while written < len(line):
        written += os.write(_PROTO_FD, line[written:])


# --- Layer 2b: resource limits -------------------------------------------------


def _apply_rlimits(mem_mb: int, cpu_secs: int) -> None:
    """Hard ceilings the kernel enforces, whatever the bot does."""

    def _set(what, soft, hard=None):
        try:
            resource.setrlimit(what, (soft, hard if hard is not None else soft))
        except (ValueError, OSError):
            pass  # not all limits exist everywhere; the namespace still applies

    _set(resource.RLIMIT_AS, mem_mb * 1024 * 1024)     # address space
    _set(resource.RLIMIT_CPU, cpu_secs)                 # total CPU for the game
    _set(resource.RLIMIT_FSIZE, 0)                      # cannot write a single byte
    _set(resource.RLIMIT_NOFILE, 64)                    # no fd exhaustion
    _set(resource.RLIMIT_CORE, 0)                       # no core dumps
    if hasattr(resource, "RLIMIT_NPROC"):
        _set(resource.RLIMIT_NPROC, 0)                  # cannot fork


def _shim_network() -> None:
    """Make socket creation fail.

    Only matters in the plain-subprocess fallback; under Docker/bwrap/unshare the
    process has no network namespace at all and this is redundant.
    """
    try:
        import socket
    except Exception:  # pragma: no cover - socket is always importable
        return

    def _blocked(*_args, **_kwargs):
        raise PermissionError("network access is not allowed in the sandbox")

    for name in ("socket", "socketpair", "create_connection", "create_server"):
        if hasattr(socket, name):
            setattr(socket, name, _blocked)
    socket.getaddrinfo = _blocked
    socket.gethostbyname = _blocked


# --- Loading the bot -----------------------------------------------------------


def _load_bot_class(path: str):
    spec = importlib.util.spec_from_file_location("participant_bot", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    bot_cls = getattr(module, "Bot", None)
    if bot_cls is None or not isinstance(bot_cls, type):
        raise ValueError("file does not define a class named 'Bot'")
    return bot_cls


def _read_line() -> str | None:
    line = sys.stdin.readline()
    return None if line == "" else line.strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bot_file")
    ap.add_argument("--mem-mb", type=int, default=512)
    ap.add_argument("--cpu-secs", type=int, default=300)
    ap.add_argument("--no-net-shim", action="store_true")
    args = ap.parse_args()

    _apply_rlimits(args.mem_mb, args.cpu_secs)
    if not args.no_net_shim:
        _shim_network()

    bot = None
    bot_cls = None

    while True:
        try:
            raw = _read_line()
        except Exception:
            return 0
        if raw is None:
            return 0
        if not raw:
            continue

        try:
            msg = json.loads(raw)
        except Exception:
            _send({"ok": False, "error": "malformed frame"})
            continue

        op = msg.get("op")

        if op == "stop":
            return 0

        if op == "init":
            try:
                bot_cls = _load_bot_class(args.bot_file)
                bot = bot_cls(msg.get("config") or {})
                _send({"ok": True})
            except BaseException as exc:  # noqa: BLE001 - participant code
                _send({"ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]})
            continue

        if op == "bid":
            if bot is None:
                _send({"ok": False, "error": "bot not initialised"})
                continue
            try:
                bid = bot.get_bid(msg.get("obs") or {})
                _send({"ok": True, "bid": bid if isinstance(bid, (int, float)) else float(bid)})
            except BaseException as exc:  # noqa: BLE001 - participant code
                _send({"ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]})
            continue

        _send({"ok": False, "error": f"unknown op {op!r}"})


if __name__ == "__main__":
    sys.exit(main())
