"""
Trading Bot Competition - submission template, VARIATION 4.

Copy this file to  <YourRollNo>_4.py  (e.g. ME24B152_4.py) and fill in
`get_bid`. This is the ONLY file you submit for variation 4. Do not rename the
class.

Test locally:  python local_test.py --bot ME24B152_4.py --variation 4

WHAT IS DIFFERENT ABOUT VARIATION 4
===================================
Variation 4 pays the top two and charges ranks three to five for it. With
b1 >= b2 >= b3 >= ... the sorted bids and X the maximum value over the players
ACTIVE that round:

    if b1 <= X:
        rank 1:  X - b2          (a second-price win)
        rank 2:  X - b1
        ranks 3, 4, 5 pay 0.5, 0.3 and 0.2 of (rank 1 + rank 2), so the round
        is exactly zero-sum. Fewer than five active players: the shares
        renormalise over the ranks that exist. Two or fewer: no penalty.
        rank 6 and below: 0

    if b1 > X:
        rank 1:  X - b1          (a loss, and the winner alone eats it)
        everyone else: 0, and no penalties are collected.

Four consequences worth thinking about before you write a line:

  1. Rank 1 pays b2, not b1. Overbidding no longer costs you directly -- it
     costs you only through the b1 > X branch, where the whole safety net is
     switched off and you eat X - b1 alone. That branch is the entire risk of
     this variation.
  2. Rank 2 is PAID here, not punished: X - b1 whenever b1 <= X. Second place
     went from the worst seat in variation 3 to a paid one.
  3. Ranks 3, 4 and 5 are the losers. Being third is strictly worse than being
     sixth -- there is no safe spot just under the money. Either commit to the
     top two or stay well clear of them.
  4. It is zero-sum in the b1 <= X branch. Whatever you make is taken from
     three specific opponents, which is why `top_bids_last_round` is handed to
     you: it is the only variation where you can see how the field below the
     top two is clustering.

You are never told X for the current round before you bid, only
`max_value_last_round`. Ranks are distinct here, so ties are broken uniformly
at random -- matching another bot's bid exactly is a coin flip, not a shared
win, and a coin flip between rank 2 (paid) and rank 3 (charged) is expensive.
"""


class Bot:
    def __init__(self, config):
        """
        Called once, before the game starts.

        config = {
            "player_id":        int,    # your index in the group
            "variation":        int,    # 4
            "num_players":      int,    # players at the start
            "num_rounds":       int,    # 2000
            "starting_capital": float,  # your capital for block 1 ONLY
            "max_bid":          float,  # your capital at construction
        }

        State you put on `self` survives the whole 2000 rounds. It is NOT
        cleared at a block boundary, which is exactly what lets you detect one.
        """
        self.config = config

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
            "my_last_rank":                  int,    # 1 or 2 = paid, 3/4/5 = you FUNDED them
            "my_last_payoff":                float,
            "max_value_last_round":          float,  # the realised X of last round
            "top_bids_last_round":           list,   # [b1, b2, b3, b4, b5] of last round
        }

        `top_bids_last_round` is always a list of five floats, zero-padded when
        fewer than five bids were made. Variation 4 is the only one that gets it.

        Everything is 0.0 in round 1, because nothing has happened yet.

        What the game does to you:
          - your capital is REDRAWN at every block boundary (every 500 rounds),
            and what you finished the previous block with does not carry over;
          - the hidden value distribution changes at the same moment, and you
            are not told when that is;
          - bid > capital, bid < 0, NaN, or no bid in time -> filed as 0;
          - hit zero capital and you sit out the REST OF THAT BLOCK, then come
            back on a fresh draw;
          - ranks 3, 4 and 5 FUND the top two. Landing just outside the money is
            the most expensive place on the board;
          - keep this under ~1 second and ~100 MB.
        """
        x = obs["x"]

        if obs["round"] > 1:
            self.seen_max.append(obs["max_value_last_round"])
            if len(self.seen_max) > 50:      # short window: it must forget a
                self.seen_max.pop(0)         # block boundary within ~50 rounds

        # ---- replace everything below with your strategy ----
        estimate_of_X = (
            sum(self.seen_max) / len(self.seen_max) if self.seen_max else x
        )

        # `top_bids_last_round[2]` is b3 -- last round's most heavily charged
        # bid, and the line you have to clear to stay out of the funded ranks.
        # Read here so you can see how; deliberately NOT acted on, because
        # chasing b3 upward is how you end up in the b1 > X branch.
        top = obs.get("top_bids_last_round") or [0.0] * 5
        third = top[2] if len(top) >= 3 else 0.0

        bid = 0.5 * estimate_of_X

        # stay legal: never above your own capital
        bid = max(0.0, min(bid, obs["capital"]))
        return bid
