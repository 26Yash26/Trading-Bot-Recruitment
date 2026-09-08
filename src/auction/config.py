"""Fixed competition parameters.

These come straight from the problem statement and do not change between runs.
Anything *hidden* (distribution bounds, the set of starting capitals used for
grading, the master seed) lives in `secret/config.py`, never here.
"""

# --- From the problem statement -------------------------------------------------

NUM_ROUNDS = 2000
"""Total rounds per game (t = 2000)."""

BLOCK_SIZE = 500
"""The x_i distribution is redrawn every BLOCK_SIZE rounds -> 4 blocks of 500."""

NUM_BLOCKS = NUM_ROUNDS // BLOCK_SIZE  # 4

HISTORY_WINDOW = 100
"""Each round, bots see bid history from the previous HISTORY_WINDOW rounds."""

GROUP_SIZE = 20
"""Bots are evaluated in randomly-drawn groups of this size."""

EVAL_REPEATS = 3
"""The full grouped simulation is repeated this many times to average out luck."""

# --- Set before the competition (announced to participants) --------------------

MAX_BID = None
"""Legal bids lie in [0, MAX_BID]. TODO: set to the value announced by organisers
(problem statement §6: 'The maximum possible bid value will also be specified
ahead of the competition')."""

# --- Engine behaviour (our decisions — keep in sync with docs/bot_interface.md) -

ELIMINATION_CAPITAL = 0.0
"""A bot with capital <= ELIMINATION_CAPITAL is out for the rest of the game.
TODO(0.B/1.B): confirm exact semantics ('<= 0' vs 'cannot afford any positive bid')."""

TIE_EPSILON = 1e-9
"""Bids within TIE_EPSILON of the max are treated as tied (all such bots win)."""
