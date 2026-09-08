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
"""Qualification iterations: the whole field is regrouped and replayed this often."""

QUALIFICATION_ITERATIONS = 3
"""Iterations 1-3 (§9). Two random, one strength-balanced by cumulative points."""

FINALS_ITERATIONS = 2
"""Iterations 4-5: the top bots play head to head on two fresh seeds."""

FINALS_SIZE = 20
"""How many bots reach the finals, by cumulative score after qualification."""

# --- Set before the competition (announced to participants) --------------------

MAX_BID = None
"""There is no fixed bid ceiling: the legal maximum is the player's own capital.

`None` means "use the player's capital", which is the rule in problem statement
§3. The engine still accepts a fixed number so its unit tests can pin payoff
arithmetic without depending on a capital draw."""

# --- Engine behaviour (our decisions — keep in sync with docs/bot_interface.md) -

ELIMINATION_CAPITAL = 0.0
"""A bot with capital <= ELIMINATION_CAPITAL is out for the rest of the game.
TODO(0.B/1.B): confirm exact semantics ('<= 0' vs 'cannot afford any positive bid')."""

TIE_EPSILON = 1e-9
"""Bids within TIE_EPSILON of the max are treated as tied (all such bots win)."""
