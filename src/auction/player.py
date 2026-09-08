"""Wrapper around a participant's bot instance.

Owns everything the engine should not care about: constructing the bot, calling
``get_bid`` and sanitising what comes back, and tracking capital + elimination.

Phase 0.C (here): plain in-process calls; a returned value that is the wrong type,
non-finite, negative, or an exception becomes an illegal bid (0). Bids above
``max_bid`` are clamped; bids above current capital become 0 (problem statement
rule 10).

Phase 1.A: the timeout + memory + no-network sandbox goes here.
"""

from __future__ import annotations

import math

from .config import ELIMINATION_CAPITAL


class Player:
    """See module docstring."""

    def __init__(
        self,
        bot_cls,
        player_id: int,
        starting_capital: float,
        variation: int,
        max_bid: float,
        num_players: int,
        num_rounds: int,
    ):
        self.id = int(player_id)
        self.starting_capital = float(starting_capital)
        self.capital = float(starting_capital)
        self.active = self.capital > ELIMINATION_CAPITAL
        self.wins = 0
        self.eliminated_round = None  # set when the bot goes inactive
        self.error_count = 0

        self._max_bid = float(max_bid)
        config = {
            "player_id": self.id,
            "variation": int(variation),
            "num_players": int(num_players),
            "num_rounds": int(num_rounds),
            "starting_capital": self.starting_capital,
            "max_bid": self._max_bid,
        }
        # A crash in the constructor is the participant's bug -- let it surface
        # here (run_local / harness decide what to do with it).
        self._bot = bot_cls(config)

    def ask(self, obs) -> float:
        """Call the bot for its bid this round and return a legal bid."""
        try:
            raw = self._bot.get_bid(obs)
        except Exception:  # noqa: BLE001 - participant code, never trust it
            self.error_count += 1
            return 0.0
        return self._sanitise(raw, obs["capital"])

    def _sanitise(self, raw, capital: float) -> float:
        try:
            bid = float(raw)
        except (TypeError, ValueError):
            self.error_count += 1
            return 0.0
        if not math.isfinite(bid) or bid < 0.0:
            self.error_count += 1
            return 0.0
        if bid > self._max_bid:
            bid = self._max_bid          # clamp into the legal range
        if bid > capital:
            return 0.0                   # illegal bid -> 0 (problem statement rule 10)
        return bid

    def settle(self, payoff: float, round_idx: int) -> None:
        """Apply a round payoff and update elimination status."""
        self.capital += float(payoff)
        if self.active and self.capital <= ELIMINATION_CAPITAL:
            self.active = False
            self.eliminated_round = int(round_idx)
