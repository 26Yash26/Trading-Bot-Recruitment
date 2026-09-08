"""Per-block value distributions.

Each block of ``BLOCK_SIZE`` rounds draws every player's ``x_i`` from a uniform
distribution ``U(lo, hi)`` whose bounds are hidden from players and change block
to block. Bounds are passed in from ``secret/config.py`` — never hard-coded here.

To implement (0.C):
    - ValueSampler(block_bounds: list[tuple[float, float]], seed: int)
        .draw(round_idx: int, n_players: int) -> np.ndarray   # shape (n_players,)
    - bounds indexed by round_idx // BLOCK_SIZE
    - fully reproducible from `seed`
"""

from __future__ import annotations


class ValueSampler:
    """Draws player values for each round. See module docstring."""

    def __init__(self, block_bounds, seed):
        raise NotImplementedError("0.C — implement per-block uniform sampling")

    def draw(self, round_idx, n_players):
        raise NotImplementedError
