"""Template for `secret/config.py` (the real file is git-ignored).

Copy to `config.py` and fill in real values before running a scored auction.

Nothing in here may ever reach a participant: these are the hidden bounds the
bots are being tested against, and knowing them turns the whole problem into
arithmetic. They are also settable from the admin console, which is the normal
route, this file is the checked-in record of what was used, for the seed
publication after the event.
"""

# Hidden uniform bounds (lo, hi) for x_i.
#
# ONLY CONSULTED WHEN THE ADMIN CONSOLE'S `bounds_mode` IS "fixed".
#
# The normal mode is "random": every iteration draws its own blocks off the
# published grids, m_b from {100, 110, ... 1000} and range from
# {100, 200, ... 1000}, M_b = m_b + range, seeded from MASTER_SEED below.
# That is what stops a schedule being learned in one showdown and carried into
# the next, and it is why these bounds are no longer the competition's main
# secret; the seed is. A hand-written schedule here is for reproducing one
# specific run, and for the engine tests, which need known bounds to pin payoff
# arithmetic against.
#
# Either one schedule of four blocks, reused by every iteration:
#
#     BLOCK_BOUNDS = [(0.0, 100.0), (40.0, 60.0), (0.0, 400.0), (5.0, 25.0)]
#
# or, preferred, and what the problem statement §9 promises, one schedule per
# iteration, so iteration 2 is a genuinely fresh set of distributions rather than
# the same ones under a new seed. Short lists cycle, so three schedules cover
# five iterations.
#
# Make the four blocks differ in BOTH scale and width. Four similar blocks mean
# there is no regime change to detect, which switches off the thing the block
# structure exists to test.
BLOCK_BOUNDS = [
    # iteration 1                                  rounds 0-499, 500-999, 1000-1499, 1500-1999
    [(0.0, 100.0), (40.0, 60.0), (0.0, 400.0), (5.0, 25.0)],
    # iteration 2
    [(10.0, 30.0), (0.0, 250.0), (60.0, 90.0), (0.0, 50.0)],
    # iteration 3 (strength-balanced groups)
    [(0.0, 75.0), (100.0, 500.0), (20.0, 40.0), (0.0, 150.0)],
    # iterations 4 and 5, the finals. Two fresh seeds, two fresh schedules.
    [(0.0, 200.0), (30.0, 45.0), (0.0, 90.0), (150.0, 600.0)],
    [(5.0, 15.0), (0.0, 320.0), (80.0, 120.0), (0.0, 60.0)],
]

# Starting capital is NOT set here. It is redrawn per player per block from the
# block's own floor and width, kappa ~ U[0.5, 2.5],
# C = m_b + (M_b - m_b) * kappa, and the multipliers are tunable
# from the admin console (`kappa_lo`, `kappa_hi`). See `src/auction/capital.py`.

# Master RNG seed. Per-run seeds are derived from this so runs are reproducible.
# Publish it after the event, with the bounds above, so results can be checked.
MASTER_SEED = 20260916
