"""Fill a local database with fake participants so the site has something to show.

    python -m scripts.seed_demo            # 18 bots across all 3 variations
    python -m scripts.seed_demo --clear    # wipe the local data directory first

Development only. It writes into ``QG_DATA_DIR`` (``.local/`` by default), which
is git-ignored and never exists on the VM. It also creates an admin session for
``demo.admin@smail.iitm.ac.in`` and prints the cookie, so the admin console can
be opened locally without configuring Google OAuth.
"""

from __future__ import annotations

import argparse
import random
import shutil

from server import config, store

# A spread of plausible strategies, so the leaderboard has a real shape instead
# of eighteen identical rows.
STRATEGIES = {
    "shade": """
class Bot:
    \"\"\"Bid a fixed fraction of the observed value.\"\"\"
    def __init__(self, config):
        self.k = {k}

    def get_bid(self, obs):
        return min(self.k * obs["x"], obs["max_bid"], obs["capital"])
""",
    "adaptive": """
class Bot:
    \"\"\"Track the recent winning bids and undercut them slightly.\"\"\"
    def __init__(self, config):
        self.margin = {k}
        self.recent = []

    def get_bid(self, obs):
        # Only last round's b1 is published now, so keep the window ourselves.
        b1 = obs.get("highest_bid_last_round") or 0.0
        if b1 > 0.0:
            self.recent.append(b1)
            del self.recent[:-20]
        target = (sum(self.recent) / len(self.recent)) if self.recent else 0.5 * obs["x"]
        bid = min(target * self.margin, 0.9 * obs["x"])
        return max(0.0, min(bid, obs["capital"]))
""",
    "cautious": """
class Bot:
    \"\"\"Bid only when the draw looks unusually high for what has been seen.\"\"\"
    def __init__(self, config):
        self.seen = []
        self.aggression = {k}

    def get_bid(self, obs):
        self.seen.append(obs["x"])
        if len(self.seen) > 200:
            self.seen.pop(0)
        typical = sum(self.seen) / len(self.seen)
        if obs["x"] < typical:
            return 0.0
        bid = self.aggression * obs["x"]
        return max(0.0, min(bid, obs["max_bid"], obs["capital"]))
""",
}

NAMES = [
    "Aditi R", "Bharath K", "Chaitanya M", "Divya S", "Eshan P", "Farhan A",
    "Gauri N", "Harsh V", "Ishita B", "Jatin L", "Kavya T", "Lakshmi D",
    "Manav G", "Nithya J", "Omkar S", "Pranav C", "Riya H", "Sahil W",
]

DEPARTMENTS = ["ME", "CS", "EE", "CH", "AE", "MM", "ED", "DA"]


def make_roll(rng: random.Random, taken: set[str]) -> str:
    while True:
        roll = (
            f"{rng.choice(DEPARTMENTS)}{rng.randint(22, 25)}"
            f"{rng.choice('BC')}{rng.randint(1, 199):03d}"
        )
        if roll not in taken:
            taken.add(roll)
            return roll


def seed(count: int, seed_value: int = 7) -> None:
    config.ensure_dirs()
    store.connect()

    rng = random.Random(seed_value)
    taken: set[str] = set()

    for index in range(count):
        roll = make_roll(rng, taken)
        name = NAMES[index % len(NAMES)]
        email = f"{roll.lower()}@smail.iitm.ac.in"
        store.upsert_user(email, name, roll)

        for variation in (1, 2, 3):
            # Not everyone enters every variation — that is allowed by the PS.
            if variation != 1 and rng.random() < 0.3:
                continue

            style = rng.choice(list(STRATEGIES))
            k = round(rng.uniform(0.35, 0.85), 3)
            source = STRATEGIES[style].format(k=k)

            path = config.SUBMISSIONS_DIR / f"{roll}_{variation}.py"
            path.write_text(source, encoding="utf-8")

            store.record_submission(
                roll=roll, variation=variation, email=email, name=name,
                filename=f"{roll}_{variation}.py", path=str(path),
                sha256=f"demo{index}{variation}", size=len(source),
                status="accepted", message="", smoke_profit=rng.uniform(-40, 120),
            )

    counts = store.submission_counts()
    print(f"  seeded {counts['participants']} participants, "
          f"{sum(counts['per_variation'].values())} bots")

    admin_email = "demo.admin@smail.iitm.ac.in"
    store.upsert_user(admin_email, "Demo Admin", "")
    token, _ = store.create_session(admin_email)
    print(f"\n  admin session cookie (add QG_ADMIN_EMAILS={admin_email}):")
    print(f"    {config.COOKIE_NAME}={token}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=18)
    parser.add_argument("--clear", action="store_true", help="wipe the data dir first")
    args = parser.parse_args()

    if args.clear and config.DATA_DIR.exists():
        shutil.rmtree(config.DATA_DIR)
        print(f"  cleared {config.DATA_DIR}")

    seed(args.count)


if __name__ == "__main__":
    main()
