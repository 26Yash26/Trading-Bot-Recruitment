# Trading Bot Competition — starter kit

Everything you need to write, test and submit a bot for the Quant Guild
recruitment auction.

```
starter-kit/
├── Template.py            ← the only file you edit
├── sample_bots/           the three bots from the problem statement
├── auction_reference/     a read-only copy of the real engine
└── README.md              this file
```

---

## 1. Set up

You need Python 3.10 or newer.

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install numpy pandas
```

## 2. Write your bot

Copy `Template.py` to `<YourRollNo>_<variation>.py` — for example
`ME24B152_1.py` for variation 1 — and fill in `get_bid`.

```python
class Bot:
    def __init__(self, config):
        """Called once, before round 0."""
        self.max_bid = config["max_bid"]

    def get_bid(self, obs):
        """Called once per round. Return a number."""
        return min(0.5 * obs["x"], obs["max_bid"], obs["capital"])
```

The class **must** be called `Bot` and `get_bid` **must** return a real number.
Everything else is yours.

### What you are given

`config`, once, at construction:

| key | meaning |
|---|---|
| `player_id` | your index in the group |
| `variation` | 1, 2 or 3 |
| `num_players` | players at the start |
| `num_rounds` | 2000 |
| `starting_capital` | what you begin with — it varies between runs |
| `max_bid` | legal bids lie in `[0, max_bid]` |

`obs`, every round:

| key | meaning |
|---|---|
| `round` | 0-indexed round number |
| `x` | **your** private value this round |
| `capital` | what you have right now |
| `num_players` | players still active |
| `max_bid` | the bid ceiling |
| `highest_bid_last_100` | highest single bid in the last ≤100 rounds |
| `second_highest_bid_last_100` | second-highest over the same window |
| `highest_bids` | per-round highest bid, oldest → newest |
| `second_highest_bids` | per-round second-highest, aligned with the above |

You never see anyone else's `x`, and you never see the distribution it was
drawn from. That distribution changes every 500 rounds.

## 3. Test it locally

```bash
python run_local.py --bot ME24B152_1.py --variation 1
```

That plays your bot against the three sample bots for a full game and prints a
capital curve and your net profit.

> The bounds used locally are a stand-in. The real ones are hidden and change
> every 500 rounds, and starting capital is varied — a bot tuned to the local
> defaults will not travel well.

## 4. Submit

Upload the file on the competition site. It is checked immediately:

1. the filename matches your roll number and a valid variation,
2. the code passes a static policy check,
3. it plays a short game against the sample bots without crashing, timing out,
   or going broke.

You get the verdict on the page. Resubmit as often as you like — the newest
accepted file per variation is the one that plays.

---

## Rules your bot has to live with

- **Under 1 second per round.** Exceed it and that round scores as a bid of 0,
  and your bot takes no further part in that game.
- **Under 100 MB.** Allocate past the sandbox ceiling and the process dies.
- **No network, no filesystem, no subprocesses.** Submissions run with no
  network namespace and a read-only filesystem. Imports are restricted to the
  standard library's computational modules plus `numpy`, `pandas`, `scipy` and
  `scikit-learn`. `eval`, `exec`, `open`, `getattr` and dunder attribute access
  are rejected before your file ever runs.
- **Bid legally.** A bid above your available capital is silently replaced with
  0 for that round. `NaN`, infinity, negatives and non-numbers are treated the
  same way. Bids above `max_bid` are clamped.
- **Any pip library is allowed in principle** — but list what you use in your
  report, and check it is on the allowlist above before you rely on it.

## The three variations

Write one file per variation. You may enter any subset.

| | Winner's payoff | Also |
|---|---|---|
| **V1** | `xᵢ − bid` (your own value) | — |
| **V2** | `X − bid` where `X = max(x)` over everyone | — |
| **V3** | `X − bid` | the second-highest bidder pays `−0.5 × (X − bid)`, or 0 if `X − bid < 0` |

Highest bid wins. If several bots tie at the top, all of them win and each
collects the full payoff.

## Reading the engine

`auction_reference/` is a copy of the code that actually runs the auction —
`engine.py` is the round loop, `variations.py` the payoff rules. It is there so
you can check exactly what happens; editing it changes nothing about how your
submission is scored.
