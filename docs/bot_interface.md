# Bot interface contract (0.B)

**Status: PROVISIONAL — needs the team's sign-off before the PS goes out.**
Open points are marked ⚠️. Once frozen, this is the contract participants code
against and the engine, `run_local.py`, sample bots and harness all follow it.

---

## The file participants submit

One file per variation, named `<RollNo>_<variation>.py` (e.g. `OB24C420_1.py`).
Each file defines exactly one class called `Bot`:

```python
class Bot:
    def __init__(self, config):
        """Called once, before round 0."""
        self.id = config["player_id"]

    def get_bid(self, obs) -> float:
        """Called once per round. Return the bid for this round."""
        return 0.5 * obs["x"]
```

- The class **must** be named `Bot`.
- `get_bid` **must** return a real number (`int` or `float`).
- No network access, no reading/writing files, no spawning processes. (Enforced
  by the sandbox in Phase 1.A — violations = disqualified.)
- < 1 second per `get_bid` call, < 100 MB resident memory (PS §6).
- Any pip-installable library is allowed, but it must be listed in the report.

---

## `config` (passed to `__init__`)

| key | type | meaning |
|---|---|---|
| `player_id` | `int` | this bot's index within its group (stable for the whole game) |
| `variation` | `int` | `1`, `2`, or `3` |
| `num_players` | `int` | players in the group at the start (before any elimination) |
| `num_rounds` | `int` | always `2000` |
| `starting_capital` | `float` | this bot's starting capital |
| `max_bid` | `float` | legal bids are in `[0, max_bid]` |

## `obs` (passed to `get_bid` every round)

| key | type | meaning |
|---|---|---|
| `round` | `int` | 0-indexed round number |
| `x` | `float` | **this bot's private value** this round (nobody else's) |
| `capital` | `float` | capital available right now |
| `num_players` | `int` | players **still active** this round |
| `max_bid` | `float` | legal bid ceiling (same as `config["max_bid"]`) |
| `highest_bid_last_100` | `float` | highest single bid seen in the last ≤100 rounds; `0.0` if none yet |
| `second_highest_bid_last_100` | `float` | second-highest single bid over the same window; `0.0` if none yet |
| ⚠️ `highest_bids` | `list[float]` | per-round highest bid, oldest→newest, len ≤ 100 |
| ⚠️ `second_highest_bids` | `list[float]` | per-round second-highest bid, aligned with `highest_bids` |

⚠️ **Decision needed:** PS §3.8 literally says bots get "the highest and second-highest
bids of the previous 100 rounds" — that reads as **two numbers**
(`highest_bid_last_100`, `second_highest_bid_last_100`). Providing the full
per-round series (`highest_bids`, `second_highest_bids`) gives strictly more
information. Pick one:
- **A — scalars only** (faithful to the PS text).
- **B — scalars + series** (more useful for adaptive strategies; still a superset,
  so nothing breaks, but we're handing out more than the PS promises).

_Current scaffold assumes B and clearly documents it; flip to A by deleting the two
series keys if the team prefers._

---

## Engine rules the bot should know (PS §3–4)

1. Highest bid wins. Ties (within `1e-9`) → **all** tied bidders win, each gets the
   full payoff.
2. Bid `> capital` → the engine silently replaces it with `0` for that round.
   Bids outside `[0, max_bid]` are clamped.
3. A returned value that is `NaN`, `inf`, negative, or not a number → treated as an
   illegal bid → `0`.
4. Payoffs (`bid` = winning bid):
   - **V1:** winner gets `x_i - bid` (winner's own value).
   - **V2:** winner gets `X - bid` where `X = max(x_i)` over all players.
   - **V3:** winner gets `X - bid`; the second-highest bidder gets
     `-0.5 * (X - bid)`, or `0` if `X - bid < 0`.
5. `capital += payoff` each round. ⚠️ **Decision needed:** a bot is eliminated when
   its capital `<= 0` (current assumption, `config.ELIMINATION_CAPITAL`) vs when it
   can no longer afford any positive bid. Eliminated bots don't return and aren't
   counted in `num_players`.

---

## Reference

`starter-kit/Template.py` is the canonical, always-in-sync copy of this contract as
runnable code. `starter-kit/auction_reference/` (built in 0.D) is a read-only copy
of `src/auction/` so participants can see exactly how rounds are simulated.
