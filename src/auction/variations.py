"""Payoff rules for the three auction variations (problem statement §4).

All three: the highest bid wins; ties -> everyone tied wins. `bid` below is the
winning bid amount.

Variation 1:  winner payoff = x_i - bid           (winner's own value)
Variation 2:  winner payoff = X   - bid           (X = max x_i over all players)
Variation 3:  winner payoff = X   - bid
              second-highest bidder pays 0.5 * (X - bid):
                  payoff_second = -0.5 * (X - bid)
                  if X - bid < 0:  payoff_second = 0

Reference sample run (problem statement §10) — used as the test fixture:
    x = [30, 50, 60], bids = [45, 55, 30], capital 100 each.
    Bot 2 (bid 55) wins; Bot 1 (bid 45) is second.
    V1: winner 50 - 55 = -5     -> caps [100, 95, 100]
    V2: winner 60 - 55 = +5     -> caps [100, 105, 100]
    V3: winner +5, second -2.5  -> caps [97.5, 105, 100]

To implement (0.C):
    payoff_v1(winner_value, winning_bid) -> float
    payoff_v2(max_value, winning_bid) -> float
    payoff_v3(max_value, winning_bid) -> (winner_payoff, second_payoff)
    resolve(bids, values, variation) -> dict of per-player payoffs
"""

from __future__ import annotations


def payoff_v1(winner_value, winning_bid):
    raise NotImplementedError("0.C")


def payoff_v2(max_value, winning_bid):
    raise NotImplementedError("0.C")


def payoff_v3(max_value, winning_bid):
    raise NotImplementedError("0.C")
