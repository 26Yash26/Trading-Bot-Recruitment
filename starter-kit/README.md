# Trading Bot Competition starter kit

Everything you need to write, test and submit a bot.

```
starter-kit/
├── Template.py       ← copy this, edit this, submit this
├── local_test.py     a rough local runner, so you can check it works
├── sample_bots/      the three bots from the problem statement
└── README.md         this file
```

Read the problem statement first. This file only explains the code; the rules,
the scoring and the timeline are in the PDF and on the competition site.

> **Variations 1 and 2 only.** Variations 3 and 4 are released after mock
> auction 1. Nothing about them is in this kit, and the site will not accept a
> `_3.py` or `_4.py` file until they open.

---

## 1. Set up

Python 3.10 or newer. Nothing to install: `local_test.py` uses only the
standard library.

```bash
python --version
```

You may use any pip-installable library in your actual bot (numpy, scipy,
whatever). Just list what you used in your report.

## 2. Write your bot

Copy `Template.py` to `<YourRollNo>_<variation>.py` (so `ME24B152_1.py` for
variation 1) and fill in `get_bid`.

```python
class Bot:
    def __init__(self, config):
        """Called once, before round 1."""
        self.id = config["player_id"]

    def get_bid(self, obs):
        """Called once per round. Return a number."""
        return min(0.5 * obs["x"], obs["capital"])
```

The class **must** be called `Bot`, and `get_bid` **must** return a real number.
Everything else is yours.

State you put on `self` survives all 2000 rounds. It is deliberately **not**
cleared at a block boundary. Noticing the boundary is part of the problem.

### `config`: handed to `__init__` once

| key | meaning |
|---|---|
| `player_id` | your index in the group, stable for the whole game |
| `variation` | `1` or `2` |
| `num_players` | players in the group at the start |
| `num_rounds` | `2000` |
| `starting_capital` | your capital **for block 1 only**; it is redrawn at every boundary |
| `max_bid` | your capital at construction; the live ceiling is `obs["max_bid"]` |

### `obs`: handed to `get_bid` every round

This is the whole of it. There is nothing else.

| key | type | V1 | V2 | meaning |
|---|---|:-:|:-:|---|
| `round` | `int` | ✓ | ✓ | 1-indexed round number, 1 … 2000 |
| `x` | `float` | ✓ | ✓ | **your** private value this round |
| `capital` | `float` | ✓ | ✓ | what you have right now |
| `max_bid` | `float` | ✓ | ✓ | your legal ceiling, which equals `capital` |
| `num_players` | `int` | ✓ | ✓ | players still solvent this round (nₜ) |
| `highest_bid_last_round` | `float` | ✓ | ✓ | b₁ of the previous round |
| `second_highest_bid_last_round` | `float` | ✓ | ✓ | b₂ of the previous round |
| `my_last_bid` | `float` | ✓ | ✓ | what you bid last round |
| `my_last_rank` | `int` | ✓ | ✓ | your rank last round; `1` means you won |
| `my_last_payoff` | `float` | ✓ | ✓ | what that was worth |
| `max_value_last_round` | `float` | no | ✓ | the realised X of the previous round |

Everything is `0.0` in round 1, because nothing has happened yet.

You are **never** told the hidden bounds, the block index, when a boundary
happens, or any other player's value, capital or identity.

## 3. Test it locally

```bash
python local_test.py --bot ME24B152_1.py --variation 1
python local_test.py --bot ME24B152_1.py --variation 1 --seed 7
```

It plays your bot against the three sample bots for a full game and prints your
capital and normalised profit block by block.

> **`local_test.py` is a rough stand-in, not the competition engine.** The
> hidden bounds it uses are made up, they change with `--seed`, and they are not
> the ones you will be scored on. You play three bots here and nineteen there.
> A good number here means your bot *runs*; it does not mean your bot is good.
> **Run several seeds** before you believe anything you see.

## 4. Submit

Upload the file on the competition site. It is checked immediately:

1. the filename matches your roll number and a variation that is currently open,
2. the code passes a static policy check,
3. it plays a short game without crashing, timing out or going broke.

You get the verdict on the page. Resubmit as often as you like. The newest
accepted file per variation is the one that plays.

---

## The blocks you are playing

Every block draws its own hidden bounds, and neither is announced:

```
m_b      from {10, 20, 30, ... 1000}        the block's minimum, step 10
range_b  from {100, 200, 300, ... 10000}    its width, step 100
M_b = m_b + range_b                         so x ~ U[m_b, M_b]
```

That is 10,000 possible blocks, spanning two orders of magnitude in **both** the
floor and the width. Three things follow, and they are the whole problem:

- **The minimum is not zero.** `x` never comes from `U[0, M]`. A block can be
  [1000, 1100], where every value sits within 10% of every other.
- **The width is not fixed.** [10, 10010] and [1000, 1100] are both ordinary
  blocks, and they are completely different games.
- **Your capital scales with the width:** not the maximum, so `κ` always means
  the same thing: how many block-widths of headroom you start with.

You are told none of it. All you ever see is your own `x` each round, and
`max_value_last_round` if your variation gets it. Working out roughly where the
block sits, and noticing when it changes, is the problem.

## Rules your bot has to live with

- **Under 1 second per round.** Exceed it and that round is filed as a bid of 0.
- **Under 100 MB.** Allocate past the ceiling and your process is killed.
- **No network, no filesystem, no subprocesses:** and no poking at the
  simulator's internals. Submissions run with no network access and a read-only
  filesystem. `eval`, `exec`, `open` and dunder attribute access are rejected
  before your file is ever imported. Doing any of this is a disqualification,
  not a warning.
- **Bid legally.** A bid above your capital, below zero, `NaN`, infinite, or not
  a number at all is replaced with **0** for that round. So is failing to return
  in time. The engine will not clamp for you, so clamp it yourself:

  ```python
  return max(0.0, min(bid, obs["capital"]))
  ```

- **Bankruptcy is per block.** Hit zero capital and you sit out the rest of
  *that block*, then come back at the next boundary on a fresh draw. You forfeit
  the remainder of the block, which is expensive. Survival is scored.

## The two variations

Write one file per variation. You may enter either, or both.

| | Winner's payoff | Everyone else |
|---|---|---|
| **V1** (private value, first price) | `xᵢ − b₁`, using the **winner's own value** | zero |
| **V2** (common value, first price) | `X − b₁`, where `X = max xᵢ` over the **active** players | zero |

Highest bid wins. If several bots tie at the top, **all** of them win and each
collects the full payoff.

In V2, `X` is the maximum over the players active *that round*: bankrupt bots
contribute no value. So as `nₜ` falls, `X` falls in expectation, and you are
told `nₜ` every round for exactly that reason.

## What actually gets you points

Not raw profit. Per block, your profit is divided by that block's hidden
maximum value, and then standardised against the other nineteen bots in your
group. Details are in the problem statement, but the practical consequences
are worth stating plainly:

- **A block is scored on its own.** Capital does not carry across a boundary.
  Four blocks, four independent tests.
- **Your capital is redrawn every block** as `m_b + range_b · κ` with
  `κ ~ U[0.5, 2.5]`. That is half to two-and-a-half block-*widths* of headroom
  above the block's floor. A bot that plays the same way on a thin bankroll as on a
  fat one is being measured, and it will show.
- **Consistency beats one good block.** Your spread across the four blocks and
  your worst block are both reported.
- **Bankruptcy is heavily penalised.** You forfeit the rest of the block.
