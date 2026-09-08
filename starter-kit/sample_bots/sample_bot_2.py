"""Sample bot 2 (problem statement §10): always bids 5 more than its own value."""


class Bot:
    def __init__(self, config):
        self.config = config

    def get_bid(self, obs):
        bid = obs["x"] + 5
        return max(0.0, min(bid, obs["max_bid"], obs["capital"]))
