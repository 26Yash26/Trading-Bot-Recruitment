# Variations 3 and 4 are released

Mock auction 1 is done, and the last two variations are open. This file is the
supplement to `README.md`; everything in that file still applies: the same
`Bot` class, the same `get_bid(obs)`, the same submission route, the same
sandbox limits, the same scoring. Only the payoff rule and one observation key
change.

```
starter-kit/
├── Template.py       variations 1 and 2
├── Template_3.py     ← new
├── Template_4.py     ← new
├── local_test.py     now runs --variation 3 and 4 as well
├── sample_bots/
├── README.md
└── README_v3_v4.md   this file
```

Submit `<YourRollNo>_3.py` and `<YourRollNo>_4.py`. You may enter any subset of
the four variations; they are ranked on separate boards.

---

## 1. The two new payoff rules

Both are **common value**: your payoff is measured against `X`, the maximum
value drawn by the players **active that round**, not against your own `xᵢ`.
Bankrupt bots contribute no value, so `X` falls as `nₜ` falls.

`b₁ ≥ b₂ ≥ b₃ ≥ …` are the round's bids, sorted descending.

### Variation 3: runner-up penalty

| Rank | Payoff |
|---|---|
| 1 | `X − b₁` |
| 2 | `−0.5 · (X − b₁)`, and **0** when `X − b₁ < 0` |
| 3 and below | 0 |

Variation 2 with second place charged. Three things follow:

1. **Second is the only losing position that costs money.** In V1 and V2 losing
   is free, so sitting just under the winner was a free option. Here it is the
   most expensive seat on the board.
2. **The penalty scales with the *winner's* surplus, not yours.** Once you are
   second you have no control over the size of it. Your only control is over how
   often you land there.
3. **A winner who overpays makes second place free.** When `X − b₁ < 0` the
   runner-up pays nothing. Aggressive rounds are safe to sit under; it is the
   quiet rounds, where the winner gets a bargain, that bill you.

### Variation 4: funded second price

If `b₁ ≤ X`:

| Rank | Payoff |
|---|---|
| 1 | `X − b₂` |
| 2 | `X − b₁` |
| 3, 4, 5 | pay `0.5`, `0.3`, `0.2` of `(rank 1 + rank 2)` |
| 6 and below | 0 |

The round is then **exactly zero-sum**. With fewer than five active players the
funding shares renormalise over the ranks that exist; with two or fewer, no
penalty is collected at all.

If `b₁ > X`: **rank 1 alone takes `X − b₁`** (a loss) and nobody else is
touched. No penalties are collected, and the round is not zero-sum.

Four things follow:

1. **Rank 1 pays `b₂`, not `b₁`.** Overbidding no longer costs you directly. It
   costs you only through the `b₁ > X` branch, where the whole structure
   switches off and you eat the loss alone. That branch is the entire risk of
   this variation.
2. **Rank 2 is paid here.** Second place went from the worst seat in V3 to a
   funded one.
3. **Ranks 3 to 5 are the losers, and rank 3 is worse than rank 6.** There is no
   safe spot just under the money. Commit to the top two or stay clear.
4. **Your gain is taken from three named opponents.** That is why V4, and only
   V4, is handed the top five bids of the previous round.

### Ties

V1 and V2 let every bidder tied at the top win in full. **V3 and V4 need
distinct ranks, so ties are broken uniformly at random.** Matching another bot's
bid exactly is a coin flip, and in V4 it is a coin flip between rank 2 (paid)
and rank 3 (charged).

---

## 2. What changes in `obs`

One new key, and it is V4-only.

| key | type | V1 | V2 | V3 | V4 | meaning |
|---|---|:-:|:-:|:-:|:-:|---|
| `max_value_last_round` | `float` | no | ✓ | ✓ | ✓ | the realised `X` of the previous round |
| `top_bids_last_round` | `list[float]` | no | no | no | ✓ | `[b₁, b₂, b₃, b₄, b₅]` of the previous round |

`top_bids_last_round` is always a list of five floats, zero-padded when fewer
than five bids were made. In round 1 everything is `0.0` and the list is all
zeros.

`my_last_rank` now matters far more than it did. In V3 a `2` means you paid. In
V4 a `3`, `4` or `5` means you funded somebody.

Every other key is unchanged. You are still never told `m_b`, `M_b`, the block
index, when a boundary happens, or any other player's value, capital or
identity.

---

## 3. Testing locally

```bash
python local_test.py --bot ME24B152_3.py --variation 3
python local_test.py --bot ME24B152_4.py --variation 4 --seed 7
```

The same warning as before applies, **and harder**. `local_test.py` seats four
bots; the competition seats twenty. V3 and V4 pay by *rank*, so the rank
structure is what the payoff depends on, and four ranks is not twenty ranks. In
V4 there is no rank 5 at this table at all, so the funding shares renormalise
over ranks 3 and 4 and the penalty each pays is larger than it would be in a
real group. A V3/V4 number here tells you your bot runs and stays legal. It
tells you nothing about whether it is good.

Run several seeds. Then submit and read the practice board.

---

## 4. Scoring is unchanged

Per block, `π = (C_end − C_start) / M_b`, standardised within your group of 20
to `P = 50 + 15·clip(z, ±3)`. Iteration score is the sum of the four block
scores; your total is the sum over iterations.

This matters more in V3 and V4 than in V1 and V2. Both are **transfer**
variations: what you gain is taken from named opponents rather than produced by
the auction. Standardisation is *within your group*, so in V3 and V4 your score
depends on who you were drawn against to a degree it never did in V1 and V2,
which is exactly why the tournament runs several iterations with fresh groups
and a strength-balanced one, and why the finals are played head to head.
