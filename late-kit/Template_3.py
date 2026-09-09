"""
Trading Bot Competition - submission template, VARIATION 3.

Copy this file to  <YourRollNo>_3.py  (e.g. ME24B152_3.py) and fill in
`get_bid`. This is the ONLY file you submit for variation 3. Do not rename the
class.

Test locally:  python local_test.py --bot ME24B152_3.py --variation 3

WHAT IS DIFFERENT ABOUT VARIATION 3
===================================
Variation 3 is variation 2 (common value, first price) with one addition: the
runner-up is punished.

    rank 1 (highest bid b1):  X - b1
    rank 2 (second bid b2):  -0.5 * (X - b1),  or 0 when X - b1 < 0
    everyone else:            0

X is the maximum value drawn by the players ACTIVE that round, not by everyone
who started the game.

Three consequences worth thinking about before you write a line:

  1. Second place is now the worst place to be. In variations 1 and 2 losing
     costs nothing, so bidding just under the winner was free. Here it is the
     only losing position that is charged, and it is charged in proportion to
     how much the winner made -- so you are punished hardest exactly when you
     were closest to a good win.
  2. The penalty is a fraction of the WINNER'S surplus, not of yours. You have
     no control over it once you are second. Your only control is over how
     often you end up there.
  3. When the winner overpays (X - b1 < 0) the runner-up pays nothing. So
     rounds where the field bids aggressively are safe to sit just under; it is
     the quiet rounds, where the winner gets a bargain, that cost you.

You are never told X for the current round before you bid, only
`max_value_last_round`. Ranks are distinct here, so ties are broken uniformly
at random -- matching another bot's bid exactly is a coin flip, not a shared
win.
"""


class Bot:
    def __init__(self, config):
        """
        Called once, before the game starts.

        config = {
            "player_id":        int,    # your index in the group
            "variation":        int,    # 3
            "num_players":      int,    # players at the start
            "num_rounds":       int,    # 2000
            "starting_capital": float,  # your capital for block 1 ONLY
            "max_bid":          float,  # your capital at construction
        }

        State you put on `self` survives the whole 2000 rounds. It is NOT
        cleared at a block boundary, which is exactly what lets you detect one.
        """
        self.config = config

        # Suggested starting point: you need an estimate of X, and the only
        # unbiased sample of it you ever get is `max_value_last_round`.
        self.seen_max = []

    def get_bid(self, obs):
        """
        Called once per round. Return your bid (a number) for this round.

        obs = {
            "round":                         int,    # 1 .. num_rounds
            "x":                             float,  # YOUR private value this round
            "capital":                       float,  # what you have right now
            "max_bid":                       float,  # == capital: your legal ceiling
            "num_players":                   int,    # players still solvent this round
            "highest_bid_last_round":        float,  # b1 of the previous round
            "second_highest_bid_last_round": float,  # b2 of the previous round
            "my_last_bid":                   float,
            "my_last_rank":                  int,    # 1 = you won, 2 = you PAID the penalty
            "my_last_payoff":                float,
            "max_value_last_round":          float,  # the realised X of last round
        }

        Everything is 0.0 in round 1, because nothing has happened yet.

        What the game does to you:
          - your capital is REDRAWN at every block boundary (every 500 rounds),
            and what you finished the previous block with does not carry over;
          - the hidden value distribution changes at the same moment, and you
            are not told when that is;
          - bid > capital, bid < 0, NaN, or no bid in time -> filed as 0;
          - hit zero capital and you sit out the REST OF THAT BLOCK, then come
            back on a fresh draw;
          - rank 2 pays -0.5 * (X - b1). Being second is not free;
          - keep this under ~1 second and ~100 MB.
        """
        x = obs["x"]

        # `max_value_last_round` is a draw of X. Averaging it estimates E[X],
        # which is what your payoff is actually measured against -- your own x
        # only tells you where you sit in the field.
        if obs["round"] > 1:
            self.seen_max.append(obs["max_value_last_round"])
            if len(self.seen_max) > 50:      # short window: it must forget a
                self.seen_max.pop(0)         # block boundary within ~50 rounds

        # ---- replace everything below with your strategy ----
        estimate_of_X = (
            sum(self.seen_max) / len(self.seen_max) if self.seen_max else x
        )
        bid = 0.5 * estimate_of_X

        # stay legal: never above your own capital
        bid = max(0.0, min(bid, obs["capital"]))
        return bid
