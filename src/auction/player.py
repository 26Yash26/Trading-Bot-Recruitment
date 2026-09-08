"""Wrapper around a participant's bot instance.

Owns everything the engine should not care about: constructing the bot, building
the per-round observation dict (docs/bot_interface.md), calling ``get_bid`` and
sanitising what comes back (non-finite / out-of-range / wrong-type -> treated as
an illegal bid), and tracking capital + elimination.

Phase 0.C: plain in-process calls, minimal validation.
Phase 1.A: add the timeout + memory sandbox here (or in a subclass).

To implement (0.C):
    Player(bot_cls, player_id, starting_capital, variation)
        .active -> bool
        .capital -> float
        .ask(observation) -> float          # calls bot.get_bid, sanitises
        .settle(payoff) -> None             # capital += payoff, update .active
"""

from __future__ import annotations


class Player:
    """See module docstring."""

    def __init__(self, bot_cls, player_id, starting_capital, variation):
        raise NotImplementedError("0.C")
