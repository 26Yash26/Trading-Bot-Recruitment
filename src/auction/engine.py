"""The round loop.

``run_game`` simulates one group of bots, one variation, for the whole game and
returns a :class:`GameResult`.

Structure (problem statement §3 and §4). The game is ``num_rounds`` rounds split
into blocks of ``block_size``. At every block boundary two things change and
neither is announced:

    * the hidden value distribution is redrawn (``distributions.ValueSampler``);
    * every player's capital is redrawn (``capital.CapitalDraw``) from that
      block's own floor and width, and a bot that went bankrupt during the
      previous block comes back.

Round procedure:
    1. draw x_i for every active player
    2. hand each active bot its observation and collect a bid
    3. a bid above the player's capital, negative, or not a number becomes 0
    4. rank the bids; variations 1 and 2 let every tied top bidder win, while
       3 and 4 need distinct ranks so ties are broken uniformly at random
    5. payoffs per variation (``variations``)
    6. capital += payoff; a bot at zero sits out the rest of *this block*
    7. remember the round's public numbers for the next round's observation

Backwards compatibility: passing ``starting_capitals`` and a finite ``max_bid``
runs the older fixed-capital model instead of redrawing per block, which is what
the engine unit tests use to pin the payoff arithmetic.
"""

from __future__ import annotations

import math
import random
import statistics
from dataclasses import asdict, dataclass, field

from . import scoring, variations
from .capital import CapitalDraw
from .config import BLOCK_SIZE, NUM_ROUNDS, TIE_EPSILON
from .distributions import ValueSampler
from .player import Player


@dataclass
class BlockSummary:
    """One player's result for one block, the unit the leaderboard scores."""

    block: int
    start_round: int
    rounds: int
    block_max: float
    start_capital: float
    end_capital: float
    normalised_profit: float
    bankrupt: bool
    points: float = 0.0

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class PlayerSummary:
    player_id: int
    starting_capital: float
    final_capital: float
    net_profit: float
    wins: int
    eliminated_round: int | None
    error_count: int
    blocks: list[BlockSummary] = field(default_factory=list)
    iteration_score: float = 0.0
    mean_normalised_profit: float = 0.0
    worst_normalised_profit: float = 0.0
    normalised_profit_spread: float = 0.0
    blocks_survived: int = 0


@dataclass
class GameResult:
    variation: int
    rounds_played: int
    players: list[PlayerSummary]
    num_blocks: int = 1
    # capital_by_round[r][i] = capital of player i at the end of round r
    capital_by_round: list[list[float]] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"Variation {self.variation}  |  {self.rounds_played} rounds "
            f"|  {self.num_blocks} blocks",
            f"  {'bot':>4}  {'score':>8}  {'mean pi':>9}  {'worst pi':>9}  "
            f"{'net':>12}  {'wins':>6}  {'alive':>6}  {'errs':>5}",
        ]
        for p in self.players:
            lines.append(
                f"  {p.player_id:>4}  {p.iteration_score:>8.1f}  "
                f"{p.mean_normalised_profit:>+9.3f}  {p.worst_normalised_profit:>+9.3f}  "
                f"{p.net_profit:>+12.2f}  {p.wins:>6}  "
                f"{p.blocks_survived:>3}/{len(p.blocks):<2}  {p.error_count:>5}"
            )
        return "\n".join(lines)


# --- bid ranking ---------------------------------------------------------------


def _top_bidders(bids: list[float]) -> list[int]:
    """Every index within ``TIE_EPSILON`` of the best bid (variations 1 and 2)."""
    top = max(bids)
    return [i for i, b in enumerate(bids) if b >= top - TIE_EPSILON]


def _rank_order(bids: list[float], rng: random.Random) -> list[int]:
    """Indices best-first, ties broken uniformly at random (variations 3 and 4).

    The shuffle happens before the sort, and Python's sort is stable, so equal
    bids keep the random order they were shuffled into.
    """
    order = list(range(len(bids)))
    rng.shuffle(order)
    order.sort(key=lambda i: -bids[i])
    return order


def _second_bidders(bids: list[float]) -> tuple[float | None, list[int]]:
    """The best bid strictly below the top, and who made it."""
    top = max(bids)
    below = [b for b in bids if b < top - TIE_EPSILON]
    if not below:
        return None, []
    second = max(below)
    return second, [i for i, b in enumerate(bids) if abs(b - second) <= TIE_EPSILON]


# --- the game ------------------------------------------------------------------


def run_game(
    bot_classes,
    *,
    variation: int,
    block_bounds,
    seed: int,
    num_rounds: int = NUM_ROUNDS,
    block_size: int = BLOCK_SIZE,
    starting_capitals=None,
    capital_draw: CapitalDraw | None = None,
    max_bid: float | None = None,
    sampler=None,
) -> GameResult:
    """Simulate one group of bots for one variation.

    bot_classes       : classes defining ``Bot(config)`` with ``get_bid(obs)``
    variation         : 1, 2, 3 or 4
    block_bounds      : list of (lo, hi) uniform bounds, one per block
    seed              : RNG seed -> reproducible run
    num_rounds        : total rounds; block_size splits them into blocks
    starting_capitals : legacy fixed-capital mode, a number, or one per bot
    capital_draw      : redraw every player's capital at each block boundary
    max_bid           : legacy fixed bid ceiling. ``None`` means the ceiling is
                        the player's own capital, which is the current rule.
    sampler           : optional injected value source (tests)
    """
    if variation not in variations.VARIATIONS:
        raise ValueError(f"variation must be one of {variations.VARIATIONS}")

    n = len(bot_classes)
    block_size = max(1, int(block_size))
    num_blocks = max(1, math.ceil(num_rounds / block_size))

    if sampler is None:
        sampler = ValueSampler(block_bounds, seed, block_size=block_size)
    rng = random.Random(seed)

    # Legacy mode keeps the capital it was handed; the current rules redraw it
    # at every block boundary from the block's own hidden maximum.
    if capital_draw is None:
        if starting_capitals is None:
            starting_capitals = 100.0
        if isinstance(starting_capitals, (int, float)):
            caps = [float(starting_capitals)] * n
        else:
            caps = [float(c) for c in starting_capitals]
            if len(caps) != n:
                raise ValueError("starting_capitals length must match bot_classes")
    else:
        first_lo, first_hi = sampler.bounds_for_round(0)
        caps = [capital_draw.draw(rng, first_lo, first_hi) for _ in range(n)]

    ceiling = math.inf if max_bid is None else float(max_bid)
    players = [
        Player(cls, i, caps[i], variation, ceiling, n, num_rounds)
        for i, cls in enumerate(bot_classes)
    ]

    capital_by_round: list[list[float]] = []
    blocks_by_player: list[list[BlockSummary]] = [[] for _ in players]
    rounds_played = 0

    # What every bot is told about the round just gone. Zeroes before round 1.
    previous = {"bids": [0.0] * 5, "max_value": 0.0}

    for block in range(num_blocks):
        start_round = block * block_size
        if start_round >= num_rounds:
            break
        block_rounds = min(block_size, num_rounds - start_round)
        block_min, block_max = (float(v) for v in sampler.bounds_for_round(start_round))

        if block > 0 and capital_draw is not None:
            for player in players:
                player.begin_block(capital_draw.draw(rng, block_min, block_max))

        block_start_caps = [p.capital for p in players]
        stopped_early = False

        for offset in range(block_rounds):
            r = start_round + offset
            active = [p for p in players if p.active]

            if len(active) < 2:
                # Fewer than two bidders is not an auction. A fresh block will
                # revive the field; if none is coming, the game is over.
                if capital_draw is None or block == num_blocks - 1:
                    stopped_early = True
                    break
                continue

            rounds_played += 1
            n_active = len(active)
            values = sampler.draw(r, n_active)
            max_value = float(max(values))

            bids: list[float] = []
            for i, p in enumerate(active):
                obs = {
                    "round": r + 1,
                    "x": float(values[i]),
                    "capital": p.capital,
                    "max_bid": p.legal_ceiling(),
                    "num_players": n_active,
                    "highest_bid_last_round": previous["bids"][0],
                    "second_highest_bid_last_round": previous["bids"][1],
                    "my_last_bid": p.last_bid,
                    "my_last_rank": p.last_rank,
                    "my_last_payoff": p.last_payoff,
                }
                if variation in variations.COMMON_VALUE:
                    obs["max_value_last_round"] = previous["max_value"]
                if variation == 4:
                    obs["top_bids_last_round"] = list(previous["bids"])
                bids.append(p.ask(obs))

            payoffs = [0.0] * n_active
            ranks = [0] * n_active

            if variation in variations.RANKED:
                order = _rank_order(bids, rng)
                for position, idx in enumerate(order, start=1):
                    ranks[idx] = position

                if variation == 3:
                    top = bids[order[0]]
                    payoffs[order[0]] = variations.payoff_v3_winner(max_value, top)
                    active[order[0]].wins += 1
                    if len(order) > 1:
                        payoffs[order[1]] = variations.payoff_v3_second(max_value, top)
                else:
                    by_rank = variations.payoff_v4(max_value, [bids[i] for i in order])
                    for position, idx in enumerate(order):
                        payoffs[idx] = by_rank[position]
                    active[order[0]].wins += 1
            else:
                winners = _top_bidders(bids)
                top = bids[winners[0]]
                second, _ = _second_bidders(bids)
                for i, bid in enumerate(bids):
                    if i in winners:
                        ranks[i] = 1
                    elif second is not None and abs(bid - second) <= TIE_EPSILON:
                        ranks[i] = 2
                    else:
                        ranks[i] = 3
                for i in winners:
                    payoffs[i] = (
                        variations.payoff_v1(values[i], top)
                        if variation == 1
                        else variations.payoff_v2(max_value, top)
                    )
                    active[i].wins += 1

            for i, p in enumerate(active):
                p.settle(payoffs[i], r, bid=bids[i], rank=ranks[i])

            ordered_bids = sorted(bids, reverse=True)[:5]
            previous = {
                "bids": (ordered_bids + [0.0] * 5)[:5],
                "max_value": max_value,
            }
            capital_by_round.append([p.capital for p in players])

        for i, p in enumerate(players):
            blocks_by_player[i].append(
                BlockSummary(
                    block=block,
                    start_round=start_round,
                    rounds=block_rounds,
                    block_max=block_max,
                    start_capital=block_start_caps[i],
                    end_capital=p.capital,
                    normalised_profit=scoring.normalised_profit(
                        block_start_caps[i], p.capital, block_max
                    ),
                    bankrupt=not p.active,
                )
            )

        if stopped_early:
            break

    # Points are relative to the rest of the group, so they can only be worked
    # out once every player's blocks are in.
    played_blocks = max((len(b) for b in blocks_by_player), default=0)
    for index in range(played_blocks):
        column = [b[index] for b in blocks_by_player if index < len(b)]
        for summary, points in zip(column, scoring.block_points(
            [b.normalised_profit for b in column]
        )):
            summary.points = points

    result_players = []
    for p, blocks in zip(players, blocks_by_player):
        pis = [b.normalised_profit for b in blocks]
        result_players.append(
            PlayerSummary(
                player_id=p.id,
                starting_capital=blocks[0].start_capital if blocks else p.starting_capital,
                final_capital=p.capital,
                net_profit=sum(b.end_capital - b.start_capital for b in blocks),
                wins=p.wins,
                eliminated_round=p.eliminated_round,
                error_count=p.error_count,
                blocks=blocks,
                iteration_score=scoring.iteration_score([b.points for b in blocks]),
                mean_normalised_profit=statistics.fmean(pis) if pis else 0.0,
                worst_normalised_profit=min(pis) if pis else 0.0,
                normalised_profit_spread=statistics.pstdev(pis) if len(pis) > 1 else 0.0,
                blocks_survived=sum(1 for b in blocks if not b.bankrupt),
            )
        )

    return GameResult(
        variation=variation,
        rounds_played=rounds_played,
        players=result_players,
        num_blocks=played_blocks,
        capital_by_round=capital_by_round,
    )
