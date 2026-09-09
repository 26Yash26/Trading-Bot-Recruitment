"""Per-block value distributions.

Each block of ``BLOCK_SIZE`` rounds draws every active player's ``x_i`` from a
uniform distribution ``U(lo, hi)`` whose bounds are hidden from players and change
block to block. Bounds are passed in (from ``secret/config.py`` in a real run) --
never hard-coded here.

Reproducible: the same ``seed`` gives the same draws, as long as ``draw`` is
called once per round in round order.
"""

from __future__ import annotations

import math

import numpy as np

from .config import BLOCK_SIZE


class ValueSampler:
    """Draws player values for each round. See module docstring."""

    def __init__(self, block_bounds, seed, block_size: int = BLOCK_SIZE):
        self._bounds = [(float(lo), float(hi)) for lo, hi in block_bounds]
        if not self._bounds:
            raise ValueError("block_bounds must have at least one (lo, hi) pair")
        for lo, hi in self._bounds:
            if hi < lo:
                raise ValueError(f"invalid block bounds: hi ({hi}) < lo ({lo})")
        self._block_size = int(block_size)
        self._rng = np.random.default_rng(seed)

    def bounds_for_round(self, round_idx: int):
        """The (lo, hi) in force for ``round_idx``. The last block's bounds are
        reused for any round beyond the supplied blocks."""
        block = int(round_idx) // self._block_size
        block = min(block, len(self._bounds) - 1)
        return self._bounds[block]

    def draw(self, round_idx: int, n_players: int) -> np.ndarray:
        """A length-``n_players`` array of values for ``round_idx``."""
        lo, hi = self.bounds_for_round(round_idx)
        return self._rng.uniform(lo, hi, size=int(n_players))


class FixedSampler:
    """Test helper: returns pre-set values per round instead of sampling.

    ``values_by_round[r]`` is the list of values for round ``r`` (one per active
    player, in player order). Used by the engine tests to reproduce the problem
    statement's sample run exactly.
    """

    def __init__(self, values_by_round):
        self._values = [np.asarray(v, dtype=float) for v in values_by_round]

    def bounds_for_round(self, round_idx: int):
        v = self._values[int(round_idx)]
        return (float(v.min()), float(v.max()))

    def draw(self, round_idx: int, n_players: int) -> np.ndarray:
        v = self._values[int(round_idx)]
        if len(v) != n_players:
            raise ValueError(
                f"round {round_idx}: expected {n_players} values, got {len(v)}"
            )
        return v


def normalise_block_bounds(value, *, num_blocks: int | None = None):
    """Coerce admin-supplied block bounds into ``[iteration][block] -> (lo, hi)``.

    Two shapes are accepted, because the tournament needs both:

    * ``[(lo, hi), ...]`` — one schedule of blocks, reused by every iteration.
      This is what a single game takes, and what the engine tests pin against.
    * ``[[(lo, hi), ...], ...]`` — a schedule per iteration, so iteration 2 faces
      genuinely different hidden distributions from iteration 1 rather than the
      same ones under a fresh seed (problem statement §9).

    Both come back in the nested form. Raises ``ValueError`` with a message fit
    to show an admin, since this is reachable from the console.
    """
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError("block bounds must be a non-empty list")

    def pair(item, where: str) -> tuple[float, float]:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise ValueError(f"{where}: each block must be a [min, max] pair")
        try:
            lo, hi = float(item[0]), float(item[1])
        except (TypeError, ValueError):
            raise ValueError(f"{where}: block bounds must be numbers") from None
        if not (math.isfinite(lo) and math.isfinite(hi)):
            raise ValueError(f"{where}: block bounds must be finite")
        if hi <= lo:
            raise ValueError(f"{where}: max ({hi}) must be greater than min ({lo})")
        if hi <= 0:
            raise ValueError(
                f"{where}: max must be positive — it is the divisor in the "
                "normalised profit, and the scale of the capital draw"
            )
        return (lo, hi)

    first = value[0]
    nested = isinstance(first, (list, tuple)) and first and isinstance(
        first[0], (list, tuple)
    )
    schedules = list(value) if nested else [value]

    out = []
    for i, schedule in enumerate(schedules):
        if not isinstance(schedule, (list, tuple)) or not schedule:
            raise ValueError(f"iteration {i + 1}: needs at least one block")
        blocks = [pair(item, f"iteration {i + 1}, block {j + 1}")
                  for j, item in enumerate(schedule)]
        if num_blocks is not None and len(blocks) != num_blocks:
            raise ValueError(
                f"iteration {i + 1}: expected {num_blocks} blocks, got {len(blocks)}"
            )
        out.append(blocks)
    return out
