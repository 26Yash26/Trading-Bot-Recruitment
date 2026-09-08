"""
Trading Bot Competition - submission template.

Copy this file to  <YourRollNo>_<variation>.py  (e.g. OB24C420_1.py) and fill in
`get_bid`. This is the ONLY file you submit. Do not rename the class.

Full spec: docs/bot_interface.md  |  Test locally:  python run_local.py --bot <file> --variation 1
"""


class Bot:
    def __init__(self, config):
        """
        Called once, before the game starts.

        config = {
            "player_id":        int,    # your index in the group
            "variation":        int,    # 1, 2, 3 or 4
            "num_players":      int,    # players at the start
            "num_rounds":       int,    # 2000
            "starting_capital": float,  # your capital for block 1 only
            "max_bid":          float,  # historical; the real ceiling is your capital
        }

        State you put on `self` survives the whole 2000 rounds. It is NOT cleared
        at a block boundary, which is exactly what lets you detect one.
        """
        self.config = config

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
            "my_last_rank":                  int,    # 1 = you won it
            "my_last_payoff":                float,

            # variations 2, 3 and 4 only:
            "max_value_last_round":          float,  # the realised X of last round

            # variation 4 only:
            "top_bids_last_round":           list,   # [b1, b2, b3, b4, b5]
        }

        Everything is 0.0 in round 1, because nothing has happened yet.

        What the game does to you:
          - your capital is REDRAWN at every block boundary (every 500 rounds) and
            what you finished the previous block with does not carry over;
          - the hidden value distribution changes at the same moment, and you are
            not told when that is;
          - bid > capital, bid < 0, NaN or no bid in time -> filed as 0;
          - hit zero capital and you sit out the REST OF THAT BLOCK, then come back
            on a fresh draw;
          - keep this under ~1 second and ~100 MB.
        """
        x = obs["x"]

        # ---- replace everything below with your strategy ----
        bid = 0.5 * x

        # stay legal: never above your own capital
        bid = max(0.0, min(bid, obs["capital"]))
        return bid
