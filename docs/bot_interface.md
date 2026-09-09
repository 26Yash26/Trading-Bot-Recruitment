# Bot interface contract

**Status: RE-FROZEN against the updated problem statement.** The
`Bot(config)` / `get_bid(obs) -> float` shape is unchanged, but the observation
set, the bid ceiling and the scoring all moved with the new PS
(`Quant_Guild_Application_updated.pdf`), so the starter kit has been rebuilt.

The engine, `run_local.py`, the sample bots, the harness and the sandbox child
protocol all follow what is below. `starter-kit/Template.py` is the runnable copy
and `starter-kit/README.md` is the participant-facing one — keep all three in sync.

Sections referenced below are from that problem statement.

---

## The file participants submit

One file per variation, named `<RollNo>_<variation>.py` (e.g. `OB24C420_1.py`,
`…_2.py`, `…_3.py`, `…_4.py`). Each file defines exactly one class called `Bot`:

```python
class Bot:
    def __init__(self, config):
        """Called once, before round 1."""
        self.id = config["player_id"]

    def get_bid(self, obs) -> float:
        """Called once per round. Return the bid for this round."""
        return min(0.5 * obs["x"], obs["capital"])
```

- The class **must** be named `Bot`.
- `get_bid` **must** return a real number (`int` or `float`).
- No network access, no reading or writing files, no spawning processes, no
  inspecting the simulator's internals. Enforced by `sandbox/` — violations are a
  disqualification.
- Under 1 second per `get_bid` call, under 100 MB resident memory (§11).
- Any pip-installable library is allowed, but it must be listed in the report.

State kept on `self` survives all 2000 rounds. It is deliberately **not** cleared
at a block boundary — detecting the boundary is part of the problem (§5).

---

## `config` (passed to `__init__`)

| key | type | meaning |
|---|---|---|
| `player_id` | `int` | this bot's index within its group (stable for the whole game) |
| `variation` | `int` | `1`, `2`, `3` or `4` |
| `num_players` | `int` | players in the group at the start |
| `num_rounds` | `int` | total rounds, normally `2000` |
| `starting_capital` | `float` | this bot's capital **for block 1 only** — it is redrawn at every boundary |
| `max_bid` | `float` | historical; the real ceiling is your capital, and `obs["max_bid"]` reports it |

## `obs` (passed to `get_bid` every round)

Exactly the table in §5, and nothing else.

| key | type | V1 | V2 | V3 | V4 | meaning |
|---|---|:-:|:-:|:-:|:-:|---|
| `round` | `int` | ✓ | ✓ | ✓ | ✓ | 1-indexed round number |
| `x` | `float` | ✓ | ✓ | ✓ | ✓ | **this bot's private value** this round |
| `capital` | `float` | ✓ | ✓ | ✓ | ✓ | capital available right now |
| `max_bid` | `float` | ✓ | ✓ | ✓ | ✓ | the legal ceiling — equal to `capital` |
| `num_players` | `int` | ✓ | ✓ | ✓ | ✓ | players **still solvent** this round (nₜ) |
| `highest_bid_last_round` | `float` | ✓ | ✓ | ✓ | ✓ | b₁ of the previous round; `0.0` in round 1 |
| `second_highest_bid_last_round` | `float` | ✓ | ✓ | ✓ | ✓ | b₂ of the previous round |
| `my_last_bid` | `float` | ✓ | ✓ | ✓ | ✓ | what this bot bid last round |
| `my_last_rank` | `int` | ✓ | ✓ | ✓ | ✓ | its rank last round; `1` means it won |
| `my_last_payoff` | `float` | ✓ | ✓ | ✓ | ✓ | what that was worth |
| `max_value_last_round` | `float` | — | ✓ | ✓ | ✓ | the realised X of the previous round |
| `top_bids_last_round` | `list[float]` | — | — | — | ✓ | `[b₁, b₂, b₃, b₄, b₅]` of the previous round |

Everything is `0.0` in round 1, because nothing has happened yet.

A bot is **never** told m_b, M_b, the block index, when a boundary occurs, or any
other player's value, capital or identity.

---

## Engine rules the bot should know (§3, §4, §6)

1. **The bid ceiling is your capital.** A bid above it, below zero, `NaN`, `inf`,
   not a number, or not returned in time is filed as `0` for that round.
2. **Blocks.** 2000 rounds split into 4 blocks of 500. At every boundary the value
   distribution is redrawn *and* every player's capital is redrawn.
   The bounds come off two grids — `m_b ∈ {10, 20, … 1000}` (step 10) and
   `range_b ∈ {100, 200, … 10000}` (step 100), with `M_b = m_b + range_b` — so
   `x ~ U[m_b, M_b]`, the minimum is never zero, and the width varies by two
   orders of magnitude. Capital is then `C = m_b + range_b · κ` with
   `κ ~ U[0.5, 2.5]`: κ block-*widths* of headroom above the block's floor.
   What you finished the previous block with does not carry over.
3. **Bankruptcy is per block.** A bot at zero capital sits out the rest of *that
   block* and returns at the next boundary on a fresh draw. While it is out it
   does not contribute a value, so it does not count towards nₜ or X.
4. **Ties.** In V1 and V2 every bidder tied at the top wins and takes the full
   payoff. V3 and V4 need distinct ranks, so ties there are broken uniformly at
   random.
5. **Payoffs** (b₁ ≥ b₂ ≥ … are the sorted bids, X is the maximum value over the
   players active that round):
   - **V1:** winner takes `x_i − b₁`; everyone else zero.
   - **V2:** winner takes `X − b₁`; everyone else zero.
   - **V3:** winner takes `X − b₁`; rank 2 pays `−0.5 · (X − b₁)`, or nothing when
     `X − b₁ < 0`.
   - **V4:** if `b₁ ≤ X`, rank 1 takes `X − b₂`, rank 2 takes `X − b₁`, and ranks
     3, 4 and 5 pay 0.5, 0.3 and 0.2 of the total the top two earned — so the round
     is exactly zero-sum. With fewer than five active players the shares
     renormalise over the ranks that exist; with two or fewer no penalty is
     collected. If `b₁ > X`, the winner alone takes `X − b₁` and nobody else is
     touched.
6. `capital += payoff` each round.

### Known engine decisions

These are ours, not the problem statement's, and are worth knowing:

- **Every bid zero.** The literal rules ("highest bid wins; ties all win") mean a
  round in which nobody bids is won by the whole field, each taking `x_i` (V1) or
  `X` (V2) for free. The engine implements this literally.
- **Fewer than two solvent players.** Not an auction, and the problem statement
  has no rule for it, so the engine skips such a round entirely — no values are
  drawn and no payoffs are assigned. The block still ends on schedule and everyone
  comes back at the next boundary.
- **Elimination threshold** is `capital <= 0` (`config.ELIMINATION_CAPITAL`),
  not "cannot afford a positive bid".

---

## Scoring (§8)

Raw profit never ranks anybody. For each player and block,
`π = (C_end − C_start) / M_b`; within each group and block those are standardised
to `P = 50 + 15 · clip(z, −3, 3)`. An iteration score is the sum of the four block
scores and a bot's total is the sum over iterations. See `src/auction/scoring.py`.

---

## Reference

`starter-kit/Template.py` is the canonical runnable copy of this contract for
variations 1 and 2; `late-kit/Template_3.py` and `late-kit/Template_4.py` are
the same for 3 and 4, staged outside the shipped directory until mock auction 1
releases them (`python build_kit.py --release-v3-v4`).

The kit ships **no engine source**. It used to carry a generated
`starter-kit/auction_reference/` copy of `src/auction/`, which handed over the
tie-break tolerance, the elimination rule, the group size, the iteration count
and both unreleased variations; it was removed in favour of a black-box local
runner. Participants get the published rules and `local_test.py`.
