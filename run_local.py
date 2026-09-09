"""Internal engine runner, plays a bot against the sample bots on the real rules.

    python run_local.py --bot some_bot.py --variation 4

This is OURS, not the participants'. Their copy is `starter-kit/local_test.py`,
which is a deliberately simplified black box and ships in the kit; this one drives
`src.auction.engine` directly, covers all four variations, and reports the same
block scores the leaderboard uses. Use it to sanity-check the engine and to try a
candidate hidden-bounds schedule before putting it in the admin console.

Unlike the participant runner, this redraws capital at every block boundary
exactly as the competition does (problem statement capital resets).
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path

from src.auction.capital import CapitalDraw
from src.auction.distributions import draw_block_bounds
from src.auction.engine import run_game
from src.auction.loader import load_bot_class

REPO_ROOT = Path(__file__).parent
SAMPLE_BOTS = [
    REPO_ROOT / "starter-kit" / "sample_bots" / f"sample_bot_{i}.py" for i in (1, 2, 3)
]

# Four blocks off the published grids, exactly as a showdown draws them
# (`distributions.draw_block_bounds`). `--bounds-seed` pins the schedule so a run
# can be repeated; leave it off and every run faces a fresh one.
DEFAULT_BOUNDS_SEED = 0


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
    ap.add_argument("--variation", type=int, choices=(1, 2, 3, 4), required=True)
    ap.add_argument("--rounds", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--bounds-seed", type=int, default=DEFAULT_BOUNDS_SEED,
                    help="pins the hidden block schedule; -1 draws a fresh one")
    ap.add_argument("--fixed-capital", type=float, default=None,
                    help="legacy fixed-capital mode; omit to redraw per block as the real game does")
    args = ap.parse_args()

    user_bot = load_bot_class(args.bot)
    sample_bots = [load_bot_class(p) for p in SAMPLE_BOTS]
    bot_classes = [user_bot, *sample_bots]

    # The default is the real rule: capital redrawn from each block's hidden
    # maximum. `--fixed-capital` is only for pinning payoff arithmetic by hand.
    num_blocks = max(1, -(-args.rounds // 500))
    bounds = draw_block_bounds(
        random.Random(None if args.bounds_seed < 0 else args.bounds_seed), num_blocks
    )
    print(f"\n  hidden blocks: {[(round(lo), round(hi)) for lo, hi in bounds]}")

    result = run_game(
        bot_classes,
        variation=args.variation,
        block_bounds=bounds,
        seed=args.seed,
        num_rounds=args.rounds,
        starting_capitals=args.fixed_capital,
        capital_draw=None if args.fixed_capital is not None else CapitalDraw(),
    )

    print()
    print(f"  bot 0 = {Path(args.bot).name};  bots 1-3 = sample bots")
    print(result.summary())
    _print_capital_curve(result)
    you = result.players[0]
    print(f"\n  bot 0: iteration score {you.iteration_score:.1f}, "
          f"mean pi {you.mean_normalised_profit:+.3f}, "
          f"worst pi {you.worst_normalised_profit:+.3f}, "
          f"survived {you.blocks_survived}/{len(you.blocks)} blocks")
    print(f"  {'block':>5}  {'M_b':>8}  {'start':>10}  {'end':>10}  {'pi':>8}  {'points':>7}")
    for b in you.blocks:
        flag = "  BANKRUPT" if b.bankrupt else ""
        print(f"  {b.block:>5}  {b.block_max:>8.1f}  {b.start_capital:>10.2f}  "
              f"{b.end_capital:>10.2f}  {b.normalised_profit:>+8.3f}  {b.points:>7.1f}{flag}")
    print(f"\n  raw net profit {you.net_profit:+.2f}, reported, but not what ranks you.")


if __name__ == "__main__":
    main()
