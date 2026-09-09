"""
Local self-test for your bot.

    python local_test.py --bot ME24B152_1.py --variation 1

Plays your bot against the three sample bots for a full 2000-round game and
prints, per block, what your capital did and your normalised profit.

WHAT THIS IS NOT
================
This is a small stand-in written so you can check that your bot runs, stays
legal and does not go broke immediately. It is NOT the competition engine, and
it does not try to be:

  * the hidden bounds [m_b, M_b] are DIFFERENT every run and are not the ones
    used to score you, a bot tuned to what you see here will not travel;
  * you play three sample bots, not nineteen real ones;
  * ties, rounding and edge cases may resolve differently here.

A good score here means your bot works. It does not mean your bot is good.
Only the auctions on the competition site count.

Public rules this file implements (all of them are in the problem statement):
  * 2000 rounds, four blocks of 500;
  * every block redraws the hidden value distribution AND your capital;
  * each block's bounds are drawn off two grids:
        m_b     from {10, 20, ..., 1000}       (100 values, step 10)
        range_b from {100, 200, ..., 10000}    (100 values, step 100)
        M_b = m_b + range_b,  and x ~ U[m_b, M_b];
  * capital: kappa ~ U[0.5, 2.5], C = m_b + range_b * kappa;
  * highest bid wins, ties all win and each collects the full payoff;
  * V1 winner takes x_i - b1, V2 winner takes X - b1, everyone else zero;
  * a bid above your capital, below zero, NaN or not a number is filed as 0;
  * capital at or below zero means you sit out the REST OF THAT BLOCK.

Only the standard library is used, so this runs anywhere Python 3.10 does.
"""

from __future__ import annotations

import argparse
import importlib.util
import math
import random
import statistics
import sys
from pathlib import Path

NUM_ROUNDS = 2000
BLOCK_SIZE = 500
HERE = Path(__file__).resolve().parent


# --- loading a bot file --------------------------------------------------------


def load_bot_class(path: Path):
    """Import `path` and hand back the `Bot` class defined in it."""
    spec = importlib.util.spec_from_file_location(f"bot_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"could not import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "Bot"):
        raise SystemExit(f"{path.name} defines no class called `Bot`")
    return module.Bot


# --- one seat at the table -----------------------------------------------------


class Seat:
    """One bot in the game, plus the bookkeeping the rules require."""

    def __init__(self, bot_cls, player_id: int, variation: int, capital: float):
        self.name = getattr(bot_cls, "__module__", "bot")
        self.id = player_id
        self.capital = float(capital)
        self.active = self.capital > 0.0
        self.wins = 0
        self.errors = 0

        # Reported back to the bot in the next round's observation.
        self.last_bid = 0.0
        self.last_rank = 0
        self.last_payoff = 0.0

        self.bot = bot_cls(
            {
                "player_id": player_id,
                "variation": variation,
                "num_players": 4,
                "num_rounds": NUM_ROUNDS,
                "starting_capital": self.capital,
                "max_bid": self.capital,
            }
        )

    def begin_block(self, capital: float) -> None:
        """Fresh capital at a block boundary. The bot object is NOT reset --
        its internal state carries across, which is what lets it notice."""
        self.capital = float(capital)
        self.active = self.capital > 0.0
        self.last_bid = 0.0
        self.last_rank = 0
        self.last_payoff = 0.0

    def ask(self, obs) -> float:
        """Call the bot and turn whatever it returns into a legal bid."""
        try:
            raw = self.bot.get_bid(obs)
        except Exception as exc:  # noqa: BLE001 - your bug, not the engine's
            self.errors += 1
            if self.errors <= 3:
                print(f"  ! bot {self.id} raised {type(exc).__name__}: {exc}")
            return 0.0
        try:
            bid = float(raw)
        except (TypeError, ValueError):
            self.errors += 1
            return 0.0
        if math.isnan(bid) or math.isinf(bid) or bid < 0.0 or bid > self.capital:
            return 0.0
        return bid

    def settle(self, payoff: float, bid: float, rank: int) -> None:
        self.capital = max(0.0, self.capital + payoff)
        self.last_bid = bid
        self.last_rank = rank
        self.last_payoff = payoff
        if self.capital <= 0.0:
            self.active = False


# --- the game ------------------------------------------------------------------


# The two grids every block's hidden bounds are drawn from. These are the real
# ones, the same code the competition runs. What you do NOT get is the seed,
# so you cannot know which of the 10,000 combinations you will actually face.
BLOCK_MIN_CHOICES = tuple(range(10, 1001, 10))        # m_b:     10 .. 1000, step 10
BLOCK_RANGE_CHOICES = tuple(range(100, 10001, 100))   # range_b: 100 .. 10000, step 100


def draw_block_bounds(rng: random.Random) -> list[tuple[float, float]]:
    """Four hidden (m_b, M_b) pairs, different every seed.

    m_b is NOT zero and the width is not fixed: blocks vary by two orders of
    magnitude in both, so `x - m_b` and `M_b - x` are different problems from one
    block to the next. A bot that assumes the values start at zero, or that they
    are "about 100", will be caught out.
    """
    bounds = []
    for _ in range(NUM_ROUNDS // BLOCK_SIZE):
        lo = float(rng.choice(BLOCK_MIN_CHOICES))
        width = float(rng.choice(BLOCK_RANGE_CHOICES))
        bounds.append((lo, lo + width))
    return bounds


def starting_capital(rng: random.Random, block_min: float, block_max: float) -> float:
    """Problem statement, capital resets: C = m_b + (M_b - m_b) * kappa.

    kappa is how many block-widths of headroom you start with. It is the same
    idea whether the block spans [10, 10010] or [1000, 1100], which is the
    point, because those are completely different games.
    """
    kappa = rng.uniform(0.5, 2.5)
    return block_min + (block_max - block_min) * kappa


def play(bot_classes, variation: int, seed: int, num_rounds: int):
    """Run the whole game and return (seats, per-block records)."""
    rng = random.Random(seed)
    bounds = draw_block_bounds(rng)
    num_blocks = max(1, math.ceil(num_rounds / BLOCK_SIZE))

    seats = [
        Seat(cls, i, variation, starting_capital(rng, *bounds[0]))
        for i, cls in enumerate(bot_classes)
    ]

    # What everyone is told about the round just gone. Zeroes before round 1.
    prev_b1 = prev_b2 = prev_max_value = 0.0
    records: list[list[dict]] = [[] for _ in seats]

    for block in range(num_blocks):
        start_round = block * BLOCK_SIZE
        if start_round >= num_rounds:
            break
        block_rounds = min(BLOCK_SIZE, num_rounds - start_round)
        lo, block_max = bounds[min(block, len(bounds) - 1)]

        if block > 0:
            for seat in seats:
                seat.begin_block(starting_capital(rng, lo, block_max))

        block_start_caps = [s.capital for s in seats]

        for offset in range(block_rounds):
            r = start_round + offset
            active = [s for s in seats if s.active]
            if len(active) < 2:
                continue  # not an auction; the next block revives the field

            values = [rng.uniform(lo, block_max) for _ in active]
            max_value = max(values)

            bids = []
            for i, seat in enumerate(active):
                obs = {
                    "round": r + 1,
                    "x": values[i],
                    "capital": seat.capital,
                    "max_bid": seat.capital,
                    "num_players": len(active),
                    "highest_bid_last_round": prev_b1,
                    "second_highest_bid_last_round": prev_b2,
                    "my_last_bid": seat.last_bid,
                    "my_last_rank": seat.last_rank,
                    "my_last_payoff": seat.last_payoff,
                }
                if variation == 2:
                    obs["max_value_last_round"] = prev_max_value
                bids.append(seat.ask(obs))

            # Highest bid wins. Every bidder tied at the top wins in full.
            top = max(bids)
            ordered = sorted(bids, reverse=True)
            second = ordered[1] if len(ordered) > 1 else 0.0

            for i, seat in enumerate(active):
                if bids[i] == top:
                    payoff = (values[i] - top) if variation == 1 else (max_value - top)
                    seat.wins += 1
                    rank = 1
                elif bids[i] == second:
                    payoff, rank = 0.0, 2
                else:
                    payoff, rank = 0.0, 3
                seat.settle(payoff, bids[i], rank)

            prev_b1, prev_b2, prev_max_value = top, second, max_value

        for i, seat in enumerate(seats):
            start = block_start_caps[i]
            records[i].append(
                {
                    "block": block,
                    "block_max": block_max,
                    "start": start,
                    "end": seat.capital,
                    "pi": (seat.capital - start) / block_max if block_max else 0.0,
                    "bankrupt": not seat.active,
                }
            )

    return seats, records


# --- output --------------------------------------------------------------------


def report(seats, records, bot_name: str) -> None:
    print()
    print(f"  bot 0 = {bot_name};  bots 1-3 = the sample bots")
    print()
    print(f"  {'bot':>4}  {'blocks survived':>15}  {'mean pi':>9}  {'worst pi':>9}  {'wins':>6}  {'errors':>7}")
    for seat, rows in zip(seats, records):
        pis = [row["pi"] for row in rows]
        survived = sum(1 for row in rows if not row["bankrupt"])
        print(
            f"  {seat.id:>4}  {survived:>12}/{len(rows):<2}  "
            f"{statistics.fmean(pis):>+9.3f}  {min(pis):>+9.3f}  "
            f"{seat.wins:>6}  {seat.errors:>7}"
        )

    print()
    print("  your blocks in detail")
    print(f"  {'block':>5}  {'start capital':>14}  {'end capital':>12}  {'pi':>8}  {'':>9}")
    for row in records[0]:
        flag = "BANKRUPT" if row["bankrupt"] else ""
        print(
            f"  {row['block']:>5}  {row['start']:>14.2f}  {row['end']:>12.2f}  "
            f"{row['pi']:>+8.3f}  {flag:>9}"
        )

    pis = [row["pi"] for row in records[0]]
    print()
    print(f"  mean pi over the four blocks: {statistics.fmean(pis):+.3f}")
    print("  pi is your block profit divided by that block's hidden maximum value.")
    print("  The competition ranks pi against the other nineteen bots in your group,")
    print("  block by block, not your raw profit. Consistency across the four")
    print("  blocks matters more than one good one, and a bankruptcy is expensive.")
    print()
    print("  Reminder: these bounds are a local stand-in and change with --seed.")
    print("  Run a few seeds before you believe anything.")


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--bot", required=True, help="path to your bot .py file")
    ap.add_argument("--variation", type=int, choices=(1, 2), required=True)
    ap.add_argument("--rounds", type=int, default=NUM_ROUNDS)
    ap.add_argument("--seed", type=int, default=0, help="changes the hidden bounds too")
    args = ap.parse_args()

    bot_path = Path(args.bot).resolve()
    if not bot_path.is_file():
        raise SystemExit(f"no such file: {bot_path}")

    sample_dir = HERE / "sample_bots"
    sample_paths = [sample_dir / f"sample_bot_{i}.py" for i in (1, 2, 3)]
    missing = [p for p in sample_paths if not p.is_file()]
    if missing:
        raise SystemExit(f"missing sample bots: {', '.join(p.name for p in missing)}")

    classes = [load_bot_class(bot_path)] + [load_bot_class(p) for p in sample_paths]

    seats, records = play(classes, args.variation, args.seed, args.rounds)
    report(seats, records, bot_path.name)

    if seats[0].errors:
        print(f"\n  WARNING: your bot raised {seats[0].errors} time(s). Every one of")
        print("  those rounds was filed as a bid of 0. Fix it before you submit.")
        sys.exit(1)


if __name__ == "__main__":
    main()
