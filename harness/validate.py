"""Accept-or-reject a single submission (build checklist 2.B).

Runs at upload time, so a participant finds out in seconds — not at the next
showdown — that their file has a syntax error or bids its whole capital away in
thirty rounds.

Three gates, cheapest first:
    1. filename + roll number shape
    2. static policy (``sandbox.policy``)
    3. a short sandboxed game against the three sample bots
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from sandbox.policy import check_source, describe
from sandbox.runner import SandboxLimits
from src.auction.capital import CapitalDraw
from src.auction.distributions import normalise_block_bounds

from .simulate import BotSpec, play_group

# ROLLNO_variation.py  — e.g. ME24B152_1.py  (problem statement §10)
FILENAME_RE = re.compile(r"^(?P<roll>[A-Z]{2}[0-9]{2}[A-Z][0-9]{3})_(?P<variation>[1234])\.py$")
ROLL_RE = re.compile(r"^[A-Z]{2}[0-9]{2}[A-Z][0-9]{3}$")

SMOKE_ROUNDS = 120
MAX_UPLOAD_BYTES = 512 * 1024


@dataclass
class ValidationResult:
    ok: bool
    reason: str = ""
    roll: str = ""
    variation: int = 0
    net_profit: float = 0.0
    wins: int = 0
    errors: int = 0
    timeouts: int = 0
    eliminated_round: int | None = None


def parse_filename(filename: str) -> tuple[str, int] | None:
    """``ME24B152_1.py`` -> ``("ME24B152", 1)``; ``None`` if it does not match."""
    match = FILENAME_RE.match(filename.strip().upper().replace(".PY", ".py"))
    if not match:
        return None
    return match.group("roll"), int(match.group("variation"))


def validate(
    filename: str,
    source: str,
    tmp_path: Path,
    *,
    expected_roll: str = "",
    block_bounds=None,
    capital_draw: CapitalDraw | None = None,
    block_size: int = SMOKE_ROUNDS,
    limits: SandboxLimits | None = None,
    tier: str | None = None,
) -> ValidationResult:
    """Check one submission. ``tmp_path`` must already hold ``source``."""
    parsed = parse_filename(filename)
    if parsed is None:
        return ValidationResult(
            ok=False,
            reason="Filename must be ROLLNO_<variation>.py, e.g. ME24B152_1.py",
        )
    roll, variation = parsed

    if expected_roll and roll != expected_roll.upper():
        return ValidationResult(
            ok=False,
            reason=f"Filename says {roll} but your roll number is {expected_roll.upper()}",
            variation=variation,
        )

    violations = check_source(source)
    if violations:
        return ValidationResult(
            ok=False,
            reason=f"Rejected by the code policy — {describe(violations)}",
            roll=roll,
            variation=variation,
        )

    # `block_bounds` comes straight off the admin settings, which may hold either
    # a flat schedule or one schedule per tournament iteration (§9) — see
    # `normalise_block_bounds`. This smoke test only ever plays one game, so it
    # always takes iteration 0's schedule; a malformed setting is refused with a
    # ValueError rather than reaching ValueSampler and crashing the request.
    try:
        schedules = normalise_block_bounds(block_bounds or [(0.0, 100.0)])
    except ValueError:
        schedules = normalise_block_bounds([(0.0, 100.0)])

    # A short game against the sample bots: does it start, survive, and bid legally?
    result = play_group(
        [BotSpec(key=roll, path=tmp_path)],
        variation=variation,
        block_bounds=schedules[0],
        seed=12345,
        num_rounds=SMOKE_ROUNDS,
        block_size=block_size,
        capital_draw=capital_draw or CapitalDraw(),
        limits=limits or SandboxLimits(),
        tier=tier,
    )
    outcome = next(o for o in result.outcomes if o.key == roll)

    if outcome.disqualified:
        return ValidationResult(
            ok=False,
            reason=f"Sandbox rejected your bot — {outcome.reason}",
            roll=roll, variation=variation,
        )
    if outcome.eliminated_round is not None:
        return ValidationResult(
            ok=False,
            reason=(
                f"Your bot went bankrupt at round {outcome.eliminated_round} of "
                f"{SMOKE_ROUNDS} against the sample bots. It would forfeit the rest "
                "of the block in a real game."
            ),
            roll=roll, variation=variation,
        )
    if outcome.errors > SMOKE_ROUNDS // 4:
        return ValidationResult(
            ok=False,
            reason=f"get_bid raised on {outcome.errors} of {SMOKE_ROUNDS} rounds",
            roll=roll, variation=variation,
        )

    return ValidationResult(
        ok=True,
        roll=roll,
        variation=variation,
        net_profit=outcome.net_profit,
        wins=outcome.wins,
        errors=outcome.errors,
        timeouts=outcome.timeouts,
        eliminated_round=outcome.eliminated_round,
    )
