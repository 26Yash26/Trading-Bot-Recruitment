"""Rolling record of per-round bid outcomes.

Feeds each bot, at the start of a round, the highest and second-highest bids from
the previous ``HISTORY_WINDOW`` (= 100) rounds. See docs/bot_interface.md for the
exact shape handed to bots.

To implement (0.C):
    BidHistory(window=HISTORY_WINDOW)
        .record(round_highest: float, round_second: float) -> None
        .highest_last_100() -> float          # 0.0 if empty
        .second_highest_last_100() -> float    # 0.0 if empty
        .highest_series() -> list[float]       # oldest -> newest, len <= window
        .second_series() -> list[float]
"""

from __future__ import annotations

from collections import deque


class BidHistory:
    """See module docstring."""

    def __init__(self, window):
        self._highest = deque(maxlen=window)
        self._second = deque(maxlen=window)

    def record(self, round_highest, round_second):
        raise NotImplementedError("0.C")
