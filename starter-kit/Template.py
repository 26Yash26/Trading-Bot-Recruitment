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
            "variation":        int,    # 1, 2 or 3
            "num_players":      int,    # players at the start
            "num_rounds":       int,    # 2000
            "starting_capital": float,
            "max_bid":          float,  # legal bids are in [0, max_bid]
        }
        """
        self.config = config
        # Put any state you want to carry between rounds on `self`.

    def get_bid(self, obs):
        """
        Called once per round. Return your bid (a number) for this round.

        obs = {
            "round":                       int,    # 0-indexed
            "x":                           float,  # YOUR private value this round
            "capital":                     float,  # what you have right now
            "num_players":                 int,    # players still active this round
            "max_bid":                     float,
            "highest_bid_last_100":        float,  # 0.0 until there is history
            "second_highest_bid_last_100": float,
            "highest_bids":                list,   # per-round highs, oldest -> newest (<=100)
            "second_highest_bids":         list,   # per-round seconds, aligned
        }

        Reminders:
          - bid > capital  -> the engine sets your bid to 0 for the round
          - bid outside [0, max_bid] is clamped
          - NaN / inf / negative / non-number -> treated as an illegal bid (0)
          - keep this under ~1 second and ~100 MB
        """
        x = obs["x"]

        # ---- replace everything below with your strategy ----
        bid = 0.5 * x

        # stay legal
        bid = max(0.0, min(bid, obs["max_bid"], obs["capital"]))
        return bid
