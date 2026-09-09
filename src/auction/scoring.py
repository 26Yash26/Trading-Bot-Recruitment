"""Turning raw block profit into leaderboard points (problem statement §8).

Raw profit is not comparable across blocks: a block whose hidden maximum is 500
pays out roughly fifty times a block whose maximum is 10, and inside one block
the players start from different capitals. So it is normalised twice.

Step 1, scale normalisation, per player per block::

    pi = (capital at the end of the block - capital at the start) / M_b

i.e. profit measured in units of that block's (hidden) maximum value. A bot that
went bankrupt ends on zero, so its pi is -C_start / M_b.

Step 2, standardisation within the group of 20, per block::

    z = clip((pi - mean) / stdev, -3, +3)          (z = 0 when stdev is 0)
    P = 50 + 15 z                                  -> [5, 95]

Clipping at three standard deviations stops one freak block from deciding the
competition. The iteration score is the sum of the four block scores, and a
bot's total is the sum over iterations.
"""

from __future__ import annotations

import statistics

Z_CLIP = 3.0
POINTS_CENTRE = 50.0
POINTS_PER_Z = 15.0


def normalised_profit(start_capital: float, end_capital: float, block_max: float) -> float:
    """Step 1: block profit in units of the block's hidden maximum value."""
    if block_max <= 0:
        return 0.0
    return (float(end_capital) - float(start_capital)) / float(block_max)


def block_points(profits) -> list[float]:
    """Step 2: standardise one block's normalised profits across the group.

    ``profits`` is every player's pi for the same block. Returns their points in
    the same order. With a degenerate block, one player, or everybody scoring
    identically, nobody is separated, so everyone sits on the centre.
    """
    values = [float(p) for p in profits]
    if not values:
        return []
    if len(values) == 1:
        return [POINTS_CENTRE]

    mean = statistics.fmean(values)
    stdev = statistics.pstdev(values)
    if stdev == 0.0:
        return [POINTS_CENTRE] * len(values)

    points = []
    for value in values:
        z = max(-Z_CLIP, min(Z_CLIP, (value - mean) / stdev))
        points.append(POINTS_CENTRE + POINTS_PER_Z * z)
    return points


def iteration_score(points) -> float:
    """One bot's score for one iteration: the sum of its four block scores."""
    return float(sum(points))
