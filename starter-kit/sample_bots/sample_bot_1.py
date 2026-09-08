"""Sample bot 1 (problem statement §10): always bids 15 more than its own value."""


class Bot:
    def __init__(self, config):
        self.config = config

    def get_bid(self, obs):
        bid = obs["x"] + 15
        # stay legal: never above the ceiling or your own capital
        return max(0.0, min(bid, obs["max_bid"], obs["capital"]))
