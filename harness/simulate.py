"""Run one group of sandboxed bots through the engine.

The engine itself is untouched: ``SandboxedBotFactory`` is callable and returns
an object with ``get_bid``, which is all ``auction.player.Player`` ever wanted
from a bot class. Everything here is about *bookkeeping* — which real
participant sat in which seat, and what the sandbox thought of them afterwards.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path

from sandbox.runner import SandboxedBotFactory, SandboxLimits
from src.auction.config import GROUP_SIZE
from src.auction.engine import run_game

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_BOTS = [
    REPO_ROOT / "starter-kit" / "sample_bots" / f"sample_bot_{i}.py" for i in (1, 2, 3)
]
FILLER_PREFIX = "__sample_"


@dataclass(frozen=True)
class BotSpec:
    """One bot in a game: who submitted it and where the file is."""

    key: str                 # roll number, or __sample_N for a filler
    path: Path
    display: str = ""

    @property
    def is_filler(self) -> bool:
        return self.key.startswith(FILLER_PREFIX)


@dataclass
class BotOutcome:
    key: str
    variation: int
    starting_capital: float
    final_capital: float
    net_profit: float
    wins: int
    rounds_played: int
    eliminated_round: int | None = None
    errors: int = 0
    timeouts: int = 0
    disqualified: bool = False
    reason: str = ""
    is_filler: bool = False


@dataclass
class GroupResult:
    variation: int
    rounds_played: int
    outcomes: list[BotOutcome] = field(default_factory=list)


def pad_to_group(specs: list[BotSpec], group_size: int = GROUP_SIZE) -> list[BotSpec]:
    """Top a short group up with sample bots so every game has a real field.

    A group of two would make the highest-bid race meaningless, so fillers are
    added up to ``group_size``. They play for real but never reach a leaderboard.
    """
    padded = list(specs)
    i = 0
    while len(padded) < group_size:
        src = SAMPLE_BOTS[i % len(SAMPLE_BOTS)]
        padded.append(BotSpec(key=f"{FILLER_PREFIX}{i}", path=src, display="Sample bot"))
        i += 1
    return padded


def make_groups(specs: list[BotSpec], group_size: int, rng: random.Random) -> list[list[BotSpec]]:
    """Random split into groups of ``group_size`` (problem statement §8).

    A trailing remainder smaller than half a group is folded into the previous
    group rather than left to play mostly against fillers.
    """
    shuffled = list(specs)
    rng.shuffle(shuffled)
    groups = [shuffled[i:i + group_size] for i in range(0, len(shuffled), group_size)]
    if len(groups) > 1 and len(groups[-1]) < max(2, group_size // 2):
        groups[-2].extend(groups.pop())
    return groups or [[]]


def play_group(
    specs: list[BotSpec],
    *,
    variation: int,
    starting_capitals,
    block_bounds,
    seed: int,
    max_bid: float,
    num_rounds: int,
    limits: SandboxLimits | None = None,
    tier: str | None = None,
) -> GroupResult:
    """Play one full game. Every bot runs in its own sandboxed process."""
    limits = limits or SandboxLimits()
    field_ = pad_to_group(specs)
    factories = [SandboxedBotFactory(s.path, limits, tier) for s in field_]

    try:
        result = run_game(
            factories,
            variation=variation,
            starting_capitals=starting_capitals,
            block_bounds=block_bounds,
            seed=seed,
            max_bid=max_bid,
            num_rounds=num_rounds,
        )
    finally:
        for factory in factories:
            factory.close()

    outcomes = []
    for spec, factory, summary in zip(field_, factories, result.players):
        bot = factory.latest
        outcomes.append(
            BotOutcome(
                key=spec.key,
                variation=variation,
                starting_capital=summary.starting_capital,
                final_capital=summary.final_capital,
                net_profit=summary.net_profit,
                wins=summary.wins,
                rounds_played=result.rounds_played,
                eliminated_round=summary.eliminated_round,
                errors=summary.error_count,
                timeouts=bot.timeouts if bot else 0,
                disqualified=bool(bot and bot.disqualified),
                reason=(bot.disqualified_reason if bot else ""),
                is_filler=spec.is_filler,
            )
        )
    return GroupResult(variation=variation, rounds_played=result.rounds_played, outcomes=outcomes)
