"""Parent side of the sandbox (layer 3): one child process per bot.

``SandboxedBotFactory`` is a drop-in for a bot *class* — the engine's
``Player`` does ``bot_cls(config)`` and then ``.get_bid(obs)``, and that is
exactly the surface a factory + proxy provide. So sandboxing costs the engine
nothing:

    factory = SandboxedBotFactory("subs/ME24B152_1.py", limits)
    result  = run_game([factory, ...], variation=1, ...)
    factory.close()

Why a process per bot rather than one process per group: a per-round wall-clock
timeout is only enforceable if the thing you kill is *just that bot*, and one
bot's crash or memory blow-up must not take its nineteen neighbours with it.

Isolation is chosen at import time by :func:`detect_isolation`, best first:

    docker   container, ``--network none``, read-only rootfs, caps dropped
    bwrap    user+net+pid namespace, read-only /usr, tmpfs cwd, no /home
    unshare  network namespace only
    sudo     dedicated low-privilege user
    plain    rlimits + in-process shims only (development fallback)
"""

from __future__ import annotations

import json
import os
import select
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

_CHILD_PY = Path(__file__).with_name("child.py")


@dataclass(frozen=True)
class SandboxLimits:
    """Everything tunable about how hard we squeeze participant code."""

    round_timeout: float = 1.0      # wall-clock seconds for one get_bid (PS §6)
    init_timeout: float = 10.0      # wall-clock seconds for Bot.__init__
    mem_mb: int = 512               # RLIMIT_AS ceiling for the child
    cpu_secs: int = 300             # total CPU seconds for a whole game
    max_consecutive_failures: int = 25
    docker_image: str = "quantguild-sandbox"
    sandbox_user: str = ""          # for the sudo tier; empty = not configured


# --- picking an isolation tier --------------------------------------------------


def _bwrap_works() -> bool:
    """Rehearse the real bind set — a probe with fewer binds passes or fails for
    reasons that say nothing about whether the actual sandbox will start."""
    if not shutil.which("bwrap"):
        return False
    try:
        return (
            subprocess.run(
                ["bwrap", *_bwrap_binds(), "--proc", "/proc", "--dev", "/dev",
                 "--tmpfs", "/tmp", "--unshare-all", "--die-with-parent",
                 "--new-session", "--clearenv", "--setenv", "PATH", "/usr/bin",
                 sys.executable, "-c", "pass"],
                capture_output=True, timeout=30,
            ).returncode == 0
        )
    except Exception:
        return False


def _unshare_works() -> bool:
    if not shutil.which("unshare"):
        return False
    try:
        return (
            subprocess.run(["unshare", "-rn", "--", sys.executable, "-c", "pass"],
                           capture_output=True, timeout=30).returncode == 0
        )
    except Exception:
        return False


def _docker_works(image: str) -> bool:
    if not shutil.which("docker"):
        return False
    try:
        return (
            subprocess.run(["docker", "image", "inspect", image],
                           capture_output=True, timeout=20).returncode == 0
        )
    except Exception:
        return False


def detect_isolation(limits: SandboxLimits | None = None) -> str:
    """Return the name of the strongest isolation tier available here."""
    limits = limits or SandboxLimits()
    if os.environ.get("QG_SANDBOX_TIER"):
        return os.environ["QG_SANDBOX_TIER"]
    if _docker_works(limits.docker_image):
        return "docker"
    if _bwrap_works():
        return "bwrap"
    if _unshare_works():
        return "unshare"
    if limits.sandbox_user and shutil.which("sudo"):
        return "sudo"
    return "plain"


def _bwrap_binds() -> list[str]:
    """Read-only /usr plus whatever /bin, /lib, ... are on this host.

    On a merged-/usr distro those are symlinks into /usr and must be recreated as
    symlinks; on an older layout they are real directories. Get this wrong and
    the dynamic linker goes missing, which surfaces as a baffling ENOENT on the
    interpreter itself.
    """
    args = ["--ro-bind", "/usr", "/usr"]
    for path in ("/bin", "/sbin", "/lib", "/lib64"):
        p = Path(path)
        if not p.exists():
            continue
        if p.is_symlink():
            args += ["--symlink", os.readlink(path), path]
        else:
            args += ["--ro-bind", path, path]
    for prefix in {sys.base_prefix, sys.prefix}:
        if not prefix.startswith("/usr"):
            args += ["--ro-bind", prefix, prefix]
    return args


def _build_argv(tier: str, bot_path: Path, limits: SandboxLimits) -> list[str]:
    """The full command line that starts one sandboxed child."""
    child_flags = [
        "--mem-mb", str(limits.mem_mb),
        "--cpu-secs", str(limits.cpu_secs),
    ]

    if tier == "docker":
        return [
            "docker", "run", "--rm", "-i",
            "--network", "none",
            "--memory", f"{limits.mem_mb}m",
            "--memory-swap", f"{limits.mem_mb}m",
            "--cpus", "1",
            "--pids-limit", "16",
            "--read-only",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "-v", f"{_CHILD_PY}:/sandbox/child.py:ro",
            "-v", f"{bot_path.resolve()}:/sandbox/bot.py:ro",
            "-w", "/tmp",
            limits.docker_image,
            "python3", "/sandbox/child.py", "/sandbox/bot.py",
            *child_flags, "--no-net-shim",
        ]

    if tier == "bwrap":
        return [
            "bwrap",
            *_bwrap_binds(),
            "--ro-bind", str(_CHILD_PY), "/sandbox/child.py",
            "--ro-bind", str(bot_path.resolve()), "/sandbox/bot.py",
            "--proc", "/proc",
            "--dev", "/dev",
            "--tmpfs", "/tmp",
            "--tmpfs", "/sandbox/work",
            "--chdir", "/sandbox/work",
            "--unshare-all",
            "--die-with-parent",
            "--new-session",
            "--clearenv",
            "--setenv", "HOME", "/sandbox/work",
            "--setenv", "PATH", "/usr/bin",
            "--setenv", "PYTHONDONTWRITEBYTECODE", "1",
            "--setenv", "OPENBLAS_NUM_THREADS", "1",
            "--setenv", "OMP_NUM_THREADS", "1",
            sys.executable, "/sandbox/child.py", "/sandbox/bot.py",
            *child_flags, "--no-net-shim",
        ]

    base = [sys.executable, str(_CHILD_PY), str(bot_path.resolve()), *child_flags]

    if tier == "unshare":
        return ["unshare", "-rn", "--", *base, "--no-net-shim"]
    if tier == "sudo":
        return ["sudo", "-n", "-u", limits.sandbox_user, "--", *base]
    return base


# --- the proxy the engine talks to ---------------------------------------------


class SandboxedBot:
    """Stands in for a participant's ``Bot`` instance, one process behind it.

    Every failure mode — timeout, crash, memory kill, garbage return value —
    surfaces as an exception, which the engine's ``Player`` already turns into a
    bid of 0 and an incremented error count.
    """

    def __init__(self, bot_path: Path, config: dict, limits: SandboxLimits, tier: str):
        self.bot_path = Path(bot_path)
        self.limits = limits
        self.tier = tier
        self.proc: subprocess.Popen | None = None
        self.alive = False
        self.disqualified = False
        self.disqualified_reason = ""
        self.timeouts = 0
        self.errors = 0
        self.consecutive_failures = 0
        self.last_error = ""
        self._buf = b""

        try:
            self._spawn()
            self._request({"op": "init", "config": config}, self.limits.init_timeout)
            self.alive = True
        except Exception as exc:  # noqa: BLE001 - any startup failure is theirs
            self._disqualify(f"init failed: {exc}"[:300])

    # -- lifecycle ---------------------------------------------------------

    def _spawn(self) -> None:
        argv = _build_argv(self.tier, self.bot_path, self.limits)
        self.proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )

    def _disqualify(self, reason: str) -> None:
        if not self.disqualified:
            self.disqualified = True
            self.disqualified_reason = reason
        self.last_error = reason
        self.alive = False
        self.close()

    def close(self) -> None:
        proc = self.proc
        if proc is None:
            return
        self.proc = None
        try:
            if proc.stdin and not proc.stdin.closed:
                proc.stdin.close()
        except Exception:
            pass
        if proc.poll() is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        try:
            proc.wait(timeout=5)
        except Exception:
            pass
        for stream in (proc.stdout, proc.stdin):
            try:
                if stream and not stream.closed:
                    stream.close()
            except Exception:
                pass

    # -- protocol ----------------------------------------------------------

    def _read_frame(self, deadline: float) -> dict:
        """Read one JSON line, or raise TimeoutError once ``deadline`` passes."""
        assert self.proc is not None and self.proc.stdout is not None
        fd = self.proc.stdout.fileno()
        while b"\n" not in self._buf:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("bot exceeded its time limit")
            ready, _, _ = select.select([fd], [], [], remaining)
            if not ready:
                raise TimeoutError("bot exceeded its time limit")
            chunk = os.read(fd, 65536)
            if not chunk:
                raise BrokenPipeError("bot process exited")
            self._buf += chunk
        line, self._buf = self._buf.split(b"\n", 1)
        return json.loads(line.decode("utf-8", errors="replace"))

    def _request(self, payload: dict, timeout: float) -> dict:
        if self.proc is None or self.proc.stdin is None:
            raise BrokenPipeError("bot process is not running")
        deadline = time.monotonic() + timeout
        self.proc.stdin.write((json.dumps(payload) + "\n").encode("utf-8"))
        self.proc.stdin.flush()
        frame = self._read_frame(deadline)
        if not frame.get("ok"):
            raise RuntimeError(str(frame.get("error", "bot error"))[:300])
        return frame

    # -- what the engine calls ---------------------------------------------

    def get_bid(self, obs) -> float:
        if self.disqualified or not self.alive:
            raise RuntimeError(self.disqualified_reason or "bot is not running")

        try:
            frame = self._request({"op": "bid", "obs": obs}, self.limits.round_timeout)
        except TimeoutError:
            self.timeouts += 1
            self.consecutive_failures += 1
            # The child is mid-computation and cannot be trusted to resync, so it
            # dies here and the bot sits out the rest of the game.
            self._disqualify(f"timed out (> {self.limits.round_timeout}s per round)")
            raise
        except (BrokenPipeError, OSError, ValueError) as exc:
            self.errors += 1
            self.consecutive_failures += 1
            self._disqualify(f"process died: {exc}"[:300])
            raise
        except RuntimeError as exc:
            # Bot raised inside get_bid: recoverable, the process is still sane.
            self.errors += 1
            self.consecutive_failures += 1
            self.last_error = str(exc)[:300]
            if self.consecutive_failures >= self.limits.max_consecutive_failures:
                self._disqualify(
                    f"{self.consecutive_failures} consecutive errors; last: {self.last_error}"
                )
            raise

        self.consecutive_failures = 0
        return frame.get("bid", 0.0)


class SandboxedBotFactory:
    """Callable that the engine treats as a bot class."""

    def __init__(self, bot_path, limits: SandboxLimits | None = None, tier: str | None = None):
        self.bot_path = Path(bot_path)
        self.limits = limits or SandboxLimits()
        self.tier = tier or detect_isolation(self.limits)
        self.instances: list[SandboxedBot] = []

    def __call__(self, config: dict) -> SandboxedBot:
        bot = SandboxedBot(self.bot_path, config, self.limits, self.tier)
        self.instances.append(bot)
        return bot

    @property
    def latest(self) -> SandboxedBot | None:
        return self.instances[-1] if self.instances else None

    def close(self) -> None:
        for bot in self.instances:
            bot.close()


def close_all(factories) -> None:
    """Close every child process spawned for a game. Always call this."""
    for factory in factories:
        try:
            factory.close()
        except Exception:
            pass
