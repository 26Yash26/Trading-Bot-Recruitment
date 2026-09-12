"""Run one group of sandboxed bots through the engine.

The engine itself is untouched: ``SandboxedBotFactory`` is callable and returns
an object with ``get_bid``, which is all ``auction.player.Player`` ever wanted
from a bot class. Everything here is about *bookkeeping*, which real
participant sat in which seat, and what the sandbox thought of them afterwards.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from pathlib import Path

from sandbox.runner import SandboxedBotFactory, SandboxLimits
from src.auction.capital import CapitalDraw
from src.auction.config import BLOCK_SIZE, GROUP_SIZE
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
    """One bot's result from one group game.

    ``iteration_score`` is what the leaderboard ranks on (problem statement §8):
    the sum of the four block scores, each of which is this bot's normalised
    block profit standardised against the other nineteen in its group.
    """

    key: str
    variation: int
    starting_capital: float
    final_capital: float
    net_profit: float
    wins: int
    rounds_played: int
    iteration_score: float = 0.0
    block_points: list[float] = field(default_factory=list)
    block_profits: list[float] = field(default_factory=list)
    mean_normalised_profit: float = 0.0
    worst_normalised_profit: float = 0.0
    normalised_profit_spread: float = 0.0
    blocks_played: int = 0
    blocks_survived: int = 0
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


def make_groups(
    specs: list[BotSpec],
    group_size: int,
    rng: random.Random,
    *,
    seeding: dict[str, float] | None = None,
) -> list[list[BotSpec]]:
    """Split the field into ``ceil(n / group_size)`` groups of near-equal size.

    Both draws use the same partition, and that is the point. Sizes differ by at
    most one, so no group is larger than ``group_size`` and every group is topped
    up to a full table with the same number of fillers give or take one.

    That matters because scoring standardises each block's profits *across the
    whole table*, fillers included (they are only dropped from the results
    afterwards). Fillers are deliberately naive, so a group carrying more of them
    is standardised against a weaker field and its real bots score higher for it.
    Splitting 54 into 20/20/14 hands six fillers to one group and none to the
    other two; 18/18/18 gives every bot the same table to be measured against.

    Without ``seeding`` the order is a shuffle, which is the blind draw
    iterations 1 and 2 use. With it, bots are sorted by cumulative points and
    dealt out in a snake, 1 to G1, 2 to G2, ..., back along the row, so groups
    end up balanced on strength rather than segregated by it.
    """
    count = max(1, math.ceil(len(specs) / group_size)) if specs else 1

    if seeding:
        ordered = sorted(specs, key=lambda s: -float(seeding.get(s.key, 0.0)))
    else:
        ordered = list(specs)
        rng.shuffle(ordered)

    groups: list[list[BotSpec]] = [[] for _ in range(count)]
    for position, spec in enumerate(ordered):
        row, column = divmod(position, count)
        # Snake, so a seeded deal alternates direction and the strongest bot in
        # one row is paired with the weakest in the next. On a shuffled order it
        # is simply an even deal.
        index = column if row % 2 == 0 else count - 1 - column
        groups[index].append(spec)
    return [g for g in groups if g] or [[]]


def play_group(
    specs: list[BotSpec],
    *,
    variation: int,
    block_bounds,
    seed: int,
    num_rounds: int,
    block_size: int = BLOCK_SIZE,
    capital_draw: CapitalDraw | None = None,
    group_size: int = GROUP_SIZE,
    limits: SandboxLimits | None = None,
    tier: str | None = None,
) -> GroupResult:
    """Play one full game. Every bot runs in its own sandboxed process."""
    limits = limits or SandboxLimits()
    field_ = pad_to_group(specs, group_size)
    factories = [SandboxedBotFactory(s.path, limits, tier) for s in field_]

    try:
        result = run_game(
            factories,
            variation=variation,
            block_bounds=block_bounds,
            seed=seed,
            num_rounds=num_rounds,
            block_size=block_size,
            capital_draw=capital_draw or CapitalDraw(),
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
                iteration_score=summary.iteration_score,
                block_points=[b.points for b in summary.blocks],
                block_profits=[b.normalised_profit for b in summary.blocks],
                mean_normalised_profit=summary.mean_normalised_profit,
                worst_normalised_profit=summary.worst_normalised_profit,
                normalised_profit_spread=summary.normalised_profit_spread,
                blocks_played=len(summary.blocks),
                blocks_survived=summary.blocks_survived,
                eliminated_round=summary.eliminated_round,
                errors=summary.error_count,
                timeouts=bot.timeouts if bot else 0,
                disqualified=bool(bot and bot.disqualified),
                reason=(bot.disqualified_reason if bot else ""),
                is_filler=spec.is_filler,
            )
        )
    return GroupResult(variation=variation, rounds_played=result.rounds_played, outcomes=outcomes)
