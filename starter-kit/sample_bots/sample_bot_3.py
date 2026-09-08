"""Sample bot 3 (problem statement §10): always bids half of its own value."""


class Bot:
    def __init__(self, config):
        self.config = config

    def get_bid(self, obs):
        bid = 0.5 * obs["x"]
        return max(0.0, min(bid, obs["max_bid"], obs["capital"]))
