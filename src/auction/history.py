"""Rolling record of per-round bid outcomes.

Each round the engine records that round's highest and second-highest bid. At the
start of a round, bots are handed the last ``HISTORY_WINDOW`` (= 100) rounds of
this record. See ``docs/bot_interface.md`` for the exact shape.

Scalar convenience fields (precise definitions -- these are our choice, documented
in the interface):
    highest_last_100()        = max over the window of each round's highest bid
    second_highest_last_100() = max over the window of each round's second bid
"""

from __future__ import annotations

from collections import deque

from .config import HISTORY_WINDOW


class BidHistory:
    """See module docstring."""

    def __init__(self, window: int = HISTORY_WINDOW):
        self._highest = deque(maxlen=window)
        self._second = deque(maxlen=window)

    def record(self, round_highest: float, round_second: float) -> None:
        self._highest.append(float(round_highest))
        self._second.append(float(round_second))

    def highest_series(self) -> list[float]:
        """Per-round highest bid, oldest -> newest, length <= window."""
        return list(self._highest)

    def second_series(self) -> list[float]:
        """Per-round second-highest bid, aligned with ``highest_series``."""
        return list(self._second)

    def highest_last_100(self) -> float:
        return max(self._highest) if self._highest else 0.0

    def second_highest_last_100(self) -> float:
        return max(self._second) if self._second else 0.0
