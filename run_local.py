"""Participant self-test harness.

    python run_local.py --bot my_bot.py --variation 1

Runs the given bot against the three sample bots for a full game and prints
capital-over-time and net profit. This is the only file participants use to test;
it must never import anything from `harness/` or `secret/`.

To implement (0.C):
    - argparse: --bot (path), --variation (1|2|3), --rounds, --seed, --capital
    - load the bot class from the file (see starter-kit/README.md for the contract)
    - call src.auction.engine.run_game with the sample bots
    - print src.auction.report.summarise(result)
"""

from __future__ import annotations


def main():
    raise NotImplementedError("0.C")


if __name__ == "__main__":
    main()
