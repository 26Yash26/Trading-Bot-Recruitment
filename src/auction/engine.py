"""The round loop.

One ``run_game`` call simulates a full 2000-round auction for one group of bots
under one variation and returns a result record (per-round capital, wins,
eliminations, final standings).

Round procedure (problem statement §3):
    1. draw x_i for every active player          (distributions.ValueSampler)
    2. collect bids from active players           (player.Player.ask)
    3. legality: bid > capital -> 0; clamp to [0, MAX_BID]
    4. winner(s) = highest bid (ties within TIE_EPSILON all win)
    5. payoffs per variation                      (variations.resolve)
    6. capital += payoff; eliminate at capital <= ELIMINATION_CAPITAL
    7. record round highest / second-highest      (history.BidHistory)
    8. next round: hand each bot its observation   (docs/bot_interface.md)

To implement (0.C):
    run_game(bot_classes, *, variation, starting_capitals, block_bounds, seed,
             num_rounds=NUM_ROUNDS) -> GameResult
"""

from __future__ import annotations


def run_game(*args, **kwargs):
    raise NotImplementedError("0.C — implement the round loop")
