"""Runtime sandbox around participant code (build checklist 1.A).

These are the tests that matter most in the whole suite: everything else
protects the fairness of the competition, this protects the machine it runs on.
Each one is a thing a participant could actually submit.
"""

from __future__ import annotations

import sys

import pytest

from sandbox.policy import check_source, describe
from sandbox.runner import SandboxedBotFactory, SandboxLimits, detect_isolation

CONFIG = {
    "player_id": 0, "variation": 1, "num_players": 4,
    "num_rounds": 10, "starting_capital": 100.0, "max_bid": 100.0,
}
OBS = {
    "round": 0, "x": 40.0, "capital": 100.0, "num_players": 4, "max_bid": 100.0,
    "highest_bid_last_100": 0.0, "second_highest_bid_last_100": 0.0,
    "highest_bids": [], "second_highest_bids": [],
}


@pytest.fixture
def run_bot(tmp_path):
    """Run one source string in the sandbox and return (bid, error, handle)."""
    if sys.platform == "win32":
        # The sandbox child talks to its parent over a subprocess pipe read with
        # select() and killed with process groups -- both POSIX-only. The sandbox
        # only ever runs on Linux (CI + the VM); the AST-policy tests below still
        # run here.
        pytest.skip("sandbox child-process IPC is POSIX-only")
    created = []

    def _run(source: str, **limit_kwargs):
        path = tmp_path / "bot.py"
        path.write_text(source, encoding="utf-8")
        limits = SandboxLimits(**{"round_timeout": 2.0, "mem_mb": 256, **limit_kwargs})
        factory = SandboxedBotFactory(path, limits)
        created.append(factory)
        bot = factory(CONFIG)
        try:
            return bot.get_bid(dict(OBS)), None, bot
        except Exception as exc:  # noqa: BLE001 - the failure is the assertion
            return None, exc, bot

    yield _run

    for factory in created:
        factory.close()


# --- the sandbox runs honest bots correctly ------------------------------------


def test_a_normal_bot_bids(run_bot):
    bid, error, _ = run_bot(
        "class Bot:\n"
        "    def __init__(self, config): self.k = 0.5\n"
        "    def get_bid(self, obs): return self.k * obs['x']\n"
    )
    assert error is None
    assert bid == pytest.approx(20.0)


def test_numpy_is_available(run_bot):
    bid, error, _ = run_bot(
        "import numpy as np\n"
        "class Bot:\n"
        "    def __init__(self, config): pass\n"
        "    def get_bid(self, obs): return float(np.mean([obs['x'], 0.0]))\n"
    )
    assert error is None
    assert bid == pytest.approx(20.0)


# --- resource limits -----------------------------------------------------------


def test_slow_bot_times_out_and_is_disqualified(run_bot):
    _, error, bot = run_bot(
        "import time\n"
        "class Bot:\n"
        "    def __init__(self, config): pass\n"
        "    def get_bid(self, obs):\n"
        "        time.sleep(30)\n"
        "        return 1.0\n",
        round_timeout=1.0,
    )
    assert isinstance(error, TimeoutError)
    assert bot.disqualified
    assert "timed out" in bot.disqualified_reason


def test_memory_hog_is_killed(run_bot):
    _, error, _ = run_bot(
        "class Bot:\n"
        "    def __init__(self, config): self.buf = []\n"
        "    def get_bid(self, obs):\n"
        "        for _ in range(40):\n"
        "            self.buf.append(bytearray(50 * 1024 * 1024))\n"
        "        return 1.0\n",
        mem_mb=256,
        round_timeout=20.0,
    )
    assert error is not None
    assert "MemoryError" in str(error) or isinstance(error, (BrokenPipeError, TimeoutError))


def test_bot_cannot_write_files(run_bot, tmp_path):
    target = tmp_path / "pwned.txt"
    _, error, _ = run_bot(
        "class Bot:\n"
        "    def __init__(self, config): pass\n"
        "    def get_bid(self, obs):\n"
        f"        open({str(target)!r}, 'w').write('x')\n"
        "        return 1.0\n"
    )
    assert error is not None
    assert not target.exists()


@pytest.mark.skipif(
    detect_isolation() == "plain",
    reason="no namespace isolation available; only the in-process shim applies",
)
def test_bot_cannot_open_sockets(run_bot):
    _, error, _ = run_bot(
        "import socket\n"
        "class Bot:\n"
        "    def __init__(self, config): pass\n"
        "    def get_bid(self, obs):\n"
        "        s = socket.socket()\n"
        "        s.settimeout(2)\n"
        "        s.connect(('1.1.1.1', 80))\n"
        "        return 1.0\n",
        round_timeout=10.0,
    )
    assert error is not None


@pytest.mark.skipif(
    detect_isolation() not in {"docker", "bwrap"},
    reason="filesystem confinement needs a container or a mount namespace",
)
def test_bot_cannot_read_the_host_filesystem(run_bot):
    _, error, _ = run_bot(
        "class Bot:\n"
        "    def __init__(self, config): pass\n"
        "    def get_bid(self, obs):\n"
        "        return float(len(open('/etc/passwd').read()))\n"
    )
    assert error is not None


# --- protocol integrity --------------------------------------------------------


def test_bot_stdout_cannot_forge_a_bid(run_bot):
    """A `print` of a well-formed protocol frame must not become the bid."""
    bid, error, _ = run_bot(
        "class Bot:\n"
        "    def __init__(self, config): pass\n"
        "    def get_bid(self, obs):\n"
        '        print(\'{"ok": true, "bid": 999999}\')\n'
        "        return 1.0\n"
    )
    assert error is None
    assert bid == pytest.approx(1.0)


def test_bot_exception_surfaces_as_an_error(run_bot):
    _, error, bot = run_bot(
        "class Bot:\n"
        "    def __init__(self, config): pass\n"
        "    def get_bid(self, obs): raise ValueError('boom')\n"
    )
    assert error is not None
    assert "boom" in str(error)
    assert bot.errors == 1


def test_constructor_failure_does_not_break_the_game(run_bot):
    _, error, bot = run_bot(
        "class Bot:\n"
        "    def __init__(self, config): raise RuntimeError('nope')\n"
        "    def get_bid(self, obs): return 1.0\n"
    )
    assert error is not None
    assert bot.disqualified
    assert "init failed" in bot.disqualified_reason


def test_repeated_errors_disqualify(run_bot, tmp_path):
    path = tmp_path / "bot.py"
    path.write_text(
        "class Bot:\n"
        "    def __init__(self, config): pass\n"
        "    def get_bid(self, obs): raise ValueError('again')\n",
        encoding="utf-8",
    )
    factory = SandboxedBotFactory(path, SandboxLimits(max_consecutive_failures=3))
    try:
        bot = factory(CONFIG)
        for _ in range(3):
            with pytest.raises(Exception):
                bot.get_bid(dict(OBS))
        assert bot.disqualified
    finally:
        factory.close()


# --- values that are not bids --------------------------------------------------


@pytest.mark.parametrize(
    "expression, expected",
    [
        ("float('nan')", float("nan")),
        ("float('inf')", float("inf")),
        ("-5.0", -5.0),
        ("10 ** 9", 10**9),
    ],
)
def test_odd_numeric_returns_reach_the_engine_for_sanitising(run_bot, expression, expected):
    """The sandbox passes numbers through; `Player._sanitise` is what rejects them.

    Keeping the two jobs separate means the sandbox has one responsibility and
    the legality rules live in exactly one place.
    """
    bid, error, _ = run_bot(
        "class Bot:\n"
        "    def __init__(self, config): pass\n"
        f"    def get_bid(self, obs): return {expression}\n"
    )
    assert error is None
    if expected != expected:  # NaN
        assert bid != bid
    else:
        assert bid == pytest.approx(expected)


def test_string_return_is_rejected(run_bot):
    _, error, _ = run_bot(
        "class Bot:\n"
        "    def __init__(self, config): pass\n"
        "    def get_bid(self, obs): return 'ten'\n"
    )
    assert error is not None


# --- the static policy ---------------------------------------------------------


@pytest.mark.parametrize(
    "source, fragment",
    [
        ("import os\nclass Bot:\n    def get_bid(self, o): return 1\n", "os"),
        ("import socket\nclass Bot:\n    def get_bid(self, o): return 1\n", "socket"),
        ("from subprocess import run\nclass Bot:\n    def get_bid(self, o): return 1\n", "subprocess"),
        ("class Bot:\n    def get_bid(self, o): return eval('1')\n", "eval"),
        ("class Bot:\n    def get_bid(self, o): return open('/x')\n", "open"),
        ("class Bot:\n    def get_bid(self, o): return getattr(o, 'x')\n", "getattr"),
        ("class Bot:\n    def get_bid(self, o): return (1).__class__\n", "__class__"),
        ("class Bot:\n    def get_bid(self, o): return o.__globals__\n", "__globals__"),
        ("class Bot:\n    def get_bid(self, o): return __import__('os')\n", "__import__"),
    ],
)
def test_policy_rejects_escape_attempts(source, fragment):
    violations = check_source(source)
    assert violations, f"expected {fragment!r} to be rejected"
    assert fragment in describe(violations)


def test_policy_defeats_string_splitting():
    """The reason this is an AST allowlist and not a substring blacklist."""
    source = (
        "class Bot:\n"
        "    def __init__(self, config): pass\n"
        "    def get_bid(self, obs):\n"
        "        name = '__cla' + 'ss__'\n"
        "        return getattr(obs, name)\n"
    )
    assert check_source(source), "getattr indirection must be rejected"


@pytest.mark.parametrize(
    "source",
    [
        "class Bot:\n    def __init__(self, c): pass\n    def get_bid(self, o): return 0.5 * o['x']\n",
        "import numpy as np\nimport math\nfrom collections import deque\n"
        "class Bot:\n    def __init__(self, c): self.q = deque(maxlen=10)\n"
        "    def get_bid(self, o): return math.sqrt(abs(o['x']))\n",
    ],
)
def test_policy_accepts_reasonable_bots(source):
    assert check_source(source) == []


def test_policy_requires_a_bot_class():
    assert check_source("def get_bid(obs):\n    return 1.0\n")


def test_detect_isolation_returns_a_known_tier():
    assert detect_isolation() in {"docker", "bwrap", "unshare", "sudo", "plain"}
