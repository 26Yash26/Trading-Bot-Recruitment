// Everything the browser is told about variations 3 and 4.
//
// This file deliberately does NOT live under `web/`. nginx serves `web/` and
// `public/` as static files and blocks `server/`, so the only way to reach this
// is `GET /api/variations/late.js`, which returns 404 until the admin switches
// variation 3 or 4 on. Before mock auction 1 there is nothing on the wire for a
// participant to read, however hard they poke at devtools.
//
// It is a real ES module, imported dynamically by `web/js/main.js`. Keep it
// dependency-free: it is fetched from a different path than the rest of the
// bundle and must not assume any relative import resolves.
//
// The payoff arithmetic here mirrors `src/auction/variations.py`. If the engine
// ever changes, change both.

export const META = {
  3: {
    name: "Runner-up Penalty",
    kind: "common value",
    formula: "X − b₁ · 2nd pays ½",
    short: "Second place is punished.",
    detail:
      "The same prize as variation 2, except the runner-up hands back half of what the winner " +
      "earned. Coming close is now actively expensive, which changes what a safe bid even means.",
    rules: [
      "The winner's payoff is <b>X − b₁</b>, exactly as in variation 2.",
      "The second-highest bidder pays <b>−0.5 × (X − b₁)</b>.",
      "If X − b₁ is negative the runner-up pays nothing, the penalty never becomes a reward.",
      "Ranks must be distinct here, so ties are broken uniformly at random.",
    ],
  },
  4: {
    name: "Funded Second Price",
    kind: "top two, ranks 3 to 5 pay",
    formula: "X − b₂ · X − b₁",
    short: "The top two are paid by ranks three to five.",
    detail:
      "Rank one takes X − b₂ and rank two takes X − b₁, funded in shares of 0.5, 0.3 and 0.2 by " +
      "ranks three, four and five. Being third is strictly worse than being sixth: there is no " +
      "safe spot just under the money.",
    rules: [
      "If <b>b₁ ≤ X</b>: rank 1 takes <b>X − b₂</b>, rank 2 takes <b>X − b₁</b>.",
      "Ranks 3, 4 and 5 pay 0.5, 0.3 and 0.2 of the total the top two earned, the round is exactly zero-sum.",
      "Fewer than five active players: the shares renormalise over the ranks that exist. Two or fewer: no penalty.",
      "If <b>b₁ > X</b>: the highest bidder alone takes X − b₁, a loss, and nobody else is touched.",
    ],
  },
};

// The observation rows that only variations 3 and 4 receive, for the rules page.
export const OBSERVATIONS = [
  ["Third, fourth and fifth highest bids of the previous round", "top_bids_last_round", [4]],
];

const signed = (n) => (n >= 0 ? `+${n.toFixed(2)}` : n.toFixed(2));

/** Your payoff on the interactive bench. Same shape as `payoff.js#evaluate`. */
export function evaluate(id, { x, bid, rival, max }) {
  const won = bid >= rival;
  const b1 = Math.max(bid, rival);
  const b2 = Math.min(bid, rival);
  const surplus = max - b1;

  if (id === 3) {
    if (won) {
      return {
        value: surplus,
        formula: `${max.toFixed(1)} − ${bid.toFixed(1)}`,
        note: `the runner-up pays ${signed(-0.5 * Math.max(0, surplus))}`,
      };
    }
    const penalty = -0.5 * Math.max(0, surplus);
    return {
      value: penalty,
      formula: `−0.5 × (${max.toFixed(1)} − ${b1.toFixed(1)})`,
      note:
        penalty === 0
          ? "the winner overpaid, so second place pays nothing"
          : "second place funds half the winner's surplus",
    };
  }

  // Variation 4.
  if (b1 > max) {
    return won
      ? {
          value: max - bid,
          formula: `${max.toFixed(1)} − ${bid.toFixed(1)}`,
          note: "b₁ > X, so the winner eats the loss alone and no penalties are collected",
        }
      : { value: 0, formula: ", ", note: "b₁ > X, so nobody but the winner is touched" };
  }
  return won
    ? {
        value: max - b2,
        formula: `${max.toFixed(1)} − ${b2.toFixed(1)}`,
        note: "rank 1 pays the second price, funded by ranks 3 to 5",
      }
    : {
        value: max - b1,
        formula: `${max.toFixed(1)} − ${b1.toFixed(1)}`,
        note: "rank 2 is paid too, it is rank 3 that you do not want to be",
      };
}

// --- worked rounds (problem statement §14) -------------------------------------

// The per-bot capitals that variation 3 adds to the three-bot worked round.
// Keyed by the bot label used in `rules.js#SAMPLE_123`. The runner-up's 97.50 is
// exactly −0.5 × the winner's +5, so this table *is* the V3 rule, which is why
// it lives here rather than in the shipped bundle.
export const SAMPLE_123_CAPS = {
  "Bot 1": { 3: "97.50" },
  "Bot 2": { 3: "105" },
  "Bot 3": { 3: "100" },
};

// §14, variation 4: six bots, capital 100 each, X = 60, b₁ = 58 ≤ X.
export const SAMPLE_4 = [
  { bot: "Bot 6", x: 55, bid: 58, rank: "1", payoff: "X − b₂ = +5", cap: "105" },
  { bot: "Bot 2", x: 50, bid: 55, rank: "2", payoff: "X − b₁ = +2", cap: "102" },
  { bot: "Bot 5", x: 45, bid: 50, rank: "3", payoff: "−0.5 × 7 = −3.5", cap: "96.5" },
  { bot: "Bot 1", x: 30, bid: 45, rank: "4", payoff: "−0.3 × 7 = −2.1", cap: "97.9" },
  { bot: "Bot 4", x: 20, bid: 40, rank: "5", payoff: "−0.2 × 7 = −1.4", cap: "98.6" },
  { bot: "Bot 3", x: 60, bid: 30, rank: "6", payoff: "0", cap: "100" },
];

/**
 * The variation 4 worked example, rendered with the rules page's own helpers so
 * it matches every other table on the page. `rules.js` passes them in rather
 * than this module importing them, because it is fetched from a different path
 * and no relative import from here would resolve.
 */
export function renderSampleFour({ table, mono, dim }) {
  return `
            <p class="mt-10 max-w-2xl text-sm leading-relaxed text-ink-2" data-fade>
              Variation 4 needs six bots to show its shape. Values 30, 50, 60, 20, 45, 55 so X = 60;
              bids 45, 55, 30, 40, 50, 58. Since b₁ = 58 ≤ X, the top two are paid and ranks 3 to 5
              fund them, T = 5 + 2 = 7. Note that Bot 3, which bid the <i>least</i>, ends the round
              better off than Bots 1, 4 and 5.
            </p>
            <div class="mt-6" data-fade>
              ${table(
                ["Bot", "Value xᵢ", "Bid", "Rank", "Payoff", "Capital"],
                SAMPLE_4.map((row) => [
                  `<b>${row.bot}</b>`,
                  mono(row.x),
                  mono(row.bid),
                  mono(row.rank),
                  dim(row.payoff),
                  mono(row.cap),
                ])
              )}
            </div>
            <p class="mt-6 text-sm leading-relaxed text-ink-2" data-fade>
              Had Bot 6 bid 62 &gt; X instead, it alone would have taken 60 − 62 = −2 and every other
              bot would have received zero. No penalties are collected in that branch.
            </p>`;
}
