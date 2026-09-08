"""Participant self-test harness.

    python run_local.py --bot my_bot.py --variation 1

Runs your bot against the three sample bots for a full game and prints
capital-over-time and net profit.

Note: the real competition uses hidden value-distribution bounds that change every
500 rounds, and starting capital is varied. The defaults here are only a
sensible stand-in so you can test locally.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from src.auction.engine import run_game
from src.auction.loader import load_bot_class

REPO_ROOT = Path(__file__).parent
SAMPLE_BOTS = [
    REPO_ROOT / "starter-kit" / "sample_bots" / f"sample_bot_{i}.py" for i in (1, 2, 3)
]

# Arbitrary stand-in bounds -- the real ones are hidden and differ. Four blocks of
# 500 rounds, deliberately not all the same so you can see regime changes matter.
DEFAULT_BLOCK_BOUNDS = [
    (0.0, 100.0),
    (25.0, 75.0),
    (0.0, 200.0),
    (40.0, 60.0),
]


def _print_capital_curve(result, n_points: int = 10) -> None:
    hist = result.capital_by_round
    if not hist:
        return
    n_players = len(hist[0])
    step = max(1, len(hist) // n_points)
    print(f"\n  capital over time (every {step} rounds)")
    header = "  " + "round".rjust(7) + "".join(f"  bot{i}".rjust(12) for i in range(n_players))
    print(header)
    for r in range(0, len(hist), step):
        row = "  " + str(r).rjust(7) + "".join(f"{c:>12.2f}" for c in hist[r])
        print(row)
    last = len(hist) - 1
    print("  " + str(last).rjust(7) + "".join(f"{c:>12.2f}" for c in hist[last]))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bot", required=True, help="path to your bot .py file")
    ap.add_argument("--variation", type=int, choices=(1, 2, 3), required=True)
    ap.add_argument("--rounds", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--capital", type=float, default=100.0, help="starting capital for every bot")
    ap.add_argument("--max-bid", type=float, default=100.0)
    args = ap.parse_args()

    user_bot = load_bot_class(args.bot)
    sample_bots = [load_bot_class(p) for p in SAMPLE_BOTS]
    bot_classes = [user_bot, *sample_bots]

    result = run_game(
        bot_classes,
        variation=args.variation,
        starting_capitals=args.capital,
        block_bounds=DEFAULT_BLOCK_BOUNDS,
        seed=args.seed,
        max_bid=args.max_bid,
        num_rounds=args.rounds,
    )

    print()
    print(f"  bot 0 = your bot ({Path(args.bot).name});  bots 1-3 = sample bots")
    print(result.summary())
    _print_capital_curve(result)
    you = result.players[0]
    print(f"\n  YOUR NET PROFIT: {you.net_profit:+.2f}  "
          f"(final capital {you.final_capital:.2f}, wins {you.wins})")


if __name__ == "__main__":
    main()
