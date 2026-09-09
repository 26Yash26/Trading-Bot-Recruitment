// The problem statement, rendered as a document rather than a PDF nobody opens.
//
// Everything here tracks the competition PDF section for section. Where a number
// is an admin setting, rounds, block size, group size, iterations, the capital
// draw, it is read from `/api/state` rather than typed in, so the page cannot
// drift from the engine that scores people.

import { store } from "../main.js";
import { attachPayoffBench, renderPayoffBench } from "../payoff.js";
import { revealAll, revealLines } from "../motion.js";
import { VARIATION_META, enabledVariations, esc } from "../ui.js";

// --- variations released later -------------------------------------------------
//
// `server/late_variations.js` is fetched from `/api/variations/late.js`, which
// 404s until the admin switches variation 3 or 4 on. Until then the module is
// absent, these helpers render nothing, and no worked example, observation row
// or payoff figure for an unreleased variation reaches the page.

let LATE = null;

/** Called by `main.js` once the late module has been imported. */
export function registerLateRules(module) {
  LATE = module || null;
}

function lateObservations() {
  return LATE?.OBSERVATIONS ?? [];
}

/** The worked-round capitals, plus any a released variation adds. */
function lateCaps(row) {
  return { ...row.caps, ...(LATE?.SAMPLE_123_CAPS?.[row.bot] ?? {}) };
}

function sampleFour(variations) {
  if (!variations.includes(4) || !LATE?.SAMPLE_4) return "";
  return LATE.renderSampleFour({ table, mono, dim });
}

const SECTIONS = [
  ["game", "The game"],
  ["capital", "Capital resets"],
  ["round", "A round"],
  ["information", "What you are told"],
  ["variations", "The variations"],
  ["scoring", "Scoring"],
  ["tournament", "Tournament"],
  ["worked", "Worked rounds"],
  ["bot", "Your bot"],
  ["submitting", "Submitting"],
  ["metrics", "How you are judged"],
];

// Problem statement §5. A tick means that variation's bot receives it.
const OBSERVATIONS = [
  ["Your own value xᵢ this round", "x", [1, 2, 3, 4]],
  ["Your current capital cᵢ, which is your maximum legal bid", "capital", [1, 2, 3, 4]],
  ["Number of active players nₜ", "num_players", [1, 2, 3, 4]],
  ["Round index t", "round", [1, 2, 3, 4]],
  ["Highest bid b₁ of the previous round", "highest_bid_last_round", [1, 2, 3, 4]],
  ["Second-highest bid b₂ of the previous round", "second_highest_bid_last_round", [1, 2, 3, 4]],
  ["Your own bid, rank and payoff last round", "my_last_bid · my_last_rank · my_last_payoff", [1, 2, 3, 4]],
  ["Realised X of the previous round", "max_value_last_round", [2, 3, 4]],
  // Rows that only an unreleased variation receives live in
  // `server/late_variations.js` and are spliced in by `lateObservations()`.
];

// §14: three bots, capital 100 each. Values 30, 50, 60 so X = 60; bids 45, 55, 30.
// A per-variation capital column is only rendered for a variation in play, so
// `caps` never carries a figure for a variation the reader is not entitled to.
const SAMPLE_123 = [
  { bot: "Bot 1", strategy: "bids xᵢ + 15", x: 30, bid: 45, caps: { 1: "100", 2: "100" } },
  { bot: "Bot 2", strategy: "bids xᵢ + 5", x: 50, bid: 55, caps: { 1: "95", 2: "105" } },
  { bot: "Bot 3", strategy: "bids 0.5 · xᵢ", x: 60, bid: 30, caps: { 1: "100", 2: "100" } },
];


const RESOURCES = [
  ["Random variables", "https://www.investopedia.com/terms/r/random-variable.asp", "Investopedia"],
  ["Python, from scratch", "https://www.w3schools.com/python/python_intro.asp", "W3Schools"],
  ["NumPy", "https://www.w3schools.com/python/numpy/numpy_intro.asp", "W3Schools"],
];

const mono = (text) => `<code class="font-mono text-xs text-flame">${esc(text)}</code>`;
const dim = (text) => `<span class="text-ink-2">${esc(text)}</span>`;

function table(headers, rows, { align = [] } = {}) {
  return `
    <div class="panel overflow-x-auto">
      <table class="w-full min-w-[38rem] text-left text-sm">
        <thead class="hair-b bg-void-3">
          <tr>${headers
            .map((h, i) => `<th class="label px-5 py-3 ${align[i] === "right" ? "text-right" : ""}">${h}</th>`)
            .join("")}</tr>
        </thead>
        <tbody class="divide-y divide-line">
          ${rows
            .map(
              (row) =>
                `<tr class="transition-colors hover:bg-void-3">${row
                  .map(
                    (cell, i) =>
                      `<td class="px-5 py-3 align-top ${
                        align[i] === "right" ? "text-right" : ""
                      }">${cell}</td>`
                  )
                  .join("")}</tr>`
            )
            .join("")}
        </tbody>
      </table>
    </div>`;
}

function heading(id, number, title) {
  return `
    <h2 id="${id}" class="rubric scroll-mt-24">
      <span class="font-mono text-[11px] tracking-[0.2em] text-flame">(${number})</span>
      <span class="d3 font-display">${title}</span>
    </h2>`;
}

function variationPanel(id, index, live) {
  const meta = VARIATION_META[id];
  return `
    <article class="card" data-reveal="${index * 70}">
      <div class="flex items-start justify-between gap-6">
        <span class="font-display text-[3rem] leading-none text-line-2" data-fade>${meta.index}</span>
        <span class="tag ${meta.edge} ${meta.ink}">${live ? esc(meta.kind) : "not released"}</span>
      </div>
      <h3 class="d4 mt-6 font-display" data-fade>${esc(meta.name)}</h3>
      <ul class="mt-5 space-y-3 text-sm leading-relaxed text-ink-2" data-fade>
        ${meta.rules
          .map(
            (rule) => `<li class="flex gap-3"><span class="${meta.ink}">▸</span><span>${rule}</span></li>`
          )
          .join("")}
      </ul>
      <div class="hair mt-7 pt-5">
        <p class="label">Winner takes</p>
        <p class="mt-2 font-mono text-sm ${meta.ink}">${esc(meta.formula)}</p>
      </div>
    </article>`;
}

export async function renderRules(app) {
  let detachBench = () => {};
  let firstPaint = true;

  const paint = () => {
    const state = store.state || {};
    const variations = enabledVariations(state);
    // V4's worked example needs six bots, so it gets its own table below.
    const threeBotColumns = variations.filter((id) => id !== 4);
    const hidden = [1, 2, 3, 4].filter((id) => !variations.includes(id));
    const rounds = state.num_rounds ?? 2000;
    const blockSize = state.block_size ?? 500;
    const blocks = state.num_blocks ?? 4;
    const groupSize = state.group_size ?? 20;
    const iterations = state.iterations ?? 3;
    const capital = state.capital || { kappa_lo: 0.5, kappa_hi: 2.5 };
    const filenames = variations.length
      ? variations.map((id) => `ROLLNO_${id}.py`).join(", ")
      : "-";
    const formUrl = (state.submission_form_url || "").trim();

    app.innerHTML = `
      <section class="bleed pt-14 pb-10" data-reveal>
        <span class="tag" data-fade>Problem statement</span>
        <h1 class="d1 mt-8 font-display">${revealLines(["The rules", "of the", "auction"])}</h1>
        <p class="lede mt-10 max-w-2xl" data-fade>
          Every participant writes a bot that plays a repeated sealed-bid auction. The highest bid
          wins the round; what winning is <i>worth</i> is what separates the variations. Below is
          everything the engine actually does. Nothing is held back except the distribution itself.
        </p>

        <div class="mt-8 flex flex-wrap gap-2" data-fade>
          <span class="tag">${esc(rounds)} rounds</span>
          <span class="tag">${esc(blocks)} blocks of ${esc(blockSize)}</span>
          <span class="tag">groups of ${esc(groupSize)}</span>
          <span class="tag">max bid = your capital</span>
          <span class="tag">1 s / round · 100 MB</span>
        </div>
      </section>

      <div class="bleed grid gap-14 pb-24 lg:grid-cols-[minmax(0,14rem)_1fr] lg:gap-20">
        <nav class="lg:sticky lg:top-24 lg:self-start" aria-label="Contents">
          <p class="label">Contents</p>
          <ul class="mt-5 space-y-0 border-l border-line">
            ${SECTIONS.map(
              ([id, title], index) => `
              <li>
                <button data-jump="${id}"
                        class="-ml-px flex w-full items-baseline gap-3 border-l-2 border-transparent py-2 pl-5
                               text-left font-mono text-[11px] uppercase tracking-[0.14em] text-ink-2
                               transition-colors hover:border-flame hover:text-ink">
                  <span class="text-[9px] text-ink-3">${String(index + 1).padStart(2, "0")}</span>
                  <span>${title}</span>
                </button>
              </li>`
            ).join("")}
          </ul>
        </nav>

        <div class="min-w-0 space-y-20">
          <div data-reveal>
            ${heading("game", "01", "The game")}
            <ul class="mt-8 space-y-4 text-sm leading-relaxed text-ink-2" data-fade>
              <li><b class="text-ink">Players.</b> ${esc(groupSize)} bots per auction group, each one
                  written by a participant.</li>
              <li><b class="text-ink">Rounds.</b> ${esc(rounds)} of them, split into ${esc(blocks)}
                  blocks of ${esc(blockSize)}.</li>
              <li><b class="text-ink">Values.</b> At the start of each round every active player draws
                  xᵢ independently from a uniform distribution. Your value tells you nothing about
                  anybody else's.</li>
              <li><b class="text-ink">Hidden regimes.</b> For block b, xᵢ ~ U[m<sub>b</sub>,
                  M<sub>b</sub>], and both bounds are hidden and different for every block. Neither
                  the bounds nor the fact that a boundary has been crossed is ever announced.
                  Detecting the regime shift is part of the problem.</li>
              <li><b class="text-ink">Maximum bid.</b> Your current capital. A bid larger than that is
                  illegal.</li>
              <li><b class="text-ink">Starting capital.</b> Redrawn at the start of every block, and
                  different for every player.</li>
            </ul>
          </div>

          <div data-reveal>
            ${heading("capital", "02", "Capital resets at every block")}
            <p class="mt-8 max-w-2xl text-sm leading-relaxed text-ink-2" data-fade>
              At the start of each block b, every player's capital is reset. For each player i
              independently:
            </p>
            <div class="panel mt-6 p-6 font-mono text-sm leading-relaxed md:p-8" data-fade>
              <p>m<sub>b</sub> ~ {10, 20, 30, … 1000}
                <span class="text-ink-3">the block's hidden minimum, in steps of 10</span></p>
              <p class="mt-2">range<sub>b</sub> ~ {100, 200, 300, … 10000}
                <span class="text-ink-3">its width, in steps of 100</span></p>
              <p class="mt-2">M<sub>b</sub> = m<sub>b</sub> + range<sub>b</sub>
                <span class="text-ink-3">so xᵢ ~ U[m<sub>b</sub>, M<sub>b</sub>]</span></p>
              <p class="mt-4">κᵢ ~ U[${esc(capital.kappa_lo)}, ${esc(capital.kappa_hi)}]</p>
              <p class="mt-2 text-flame">C⁽ᵇ'⁰⁾ᵢ = m<sub>b</sub> + range<sub>b</sub> · κᵢ</p>
            </div>
            <p class="mt-6 max-w-2xl text-sm leading-relaxed text-ink-2" data-fade>
              Both grids hold 100 values, so there are <b class="text-ink">10,000</b> possible blocks
              and they span two orders of magnitude in <em>both</em> the floor and the width. The
              minimum is not zero, and a block as narrow as [1000, 1100] is as likely as one as wide
              as [10, 10010], a bot that assumes values start at zero, or that they are "about a
              hundred", is being measured on exactly that assumption.
            </p>
            <p class="mt-4 max-w-2xl text-sm leading-relaxed text-ink-2" data-fade>
              Capital scales with the <em>width</em>, not the maximum, so κ always means the same
              thing: how many block-widths of headroom you start with. Nothing is announced, not
              m<sub>b</sub>, not the range, not when a block changes.
            </p>
            <div class="mt-8 grid gap-px bg-line md:grid-cols-2" data-fade>
              <div class="bg-void p-6 md:p-8">
                <h3 class="d4 font-display">It does not carry over</h3>
                <p class="mt-4 text-sm leading-relaxed text-ink-2">
                  The capital you finish a block with is banked separately, normalised, and converted
                  into leaderboard points. The next block starts from a freshly drawn capital. Inside
                  one block some bots start rich and some start poor, and nobody is told anyone
                  else's number.
                </p>
              </div>
              <div class="bg-void p-6 md:p-8">
                <h3 class="d4 font-display">Why it is reset</h3>
                <p class="mt-4 text-sm leading-relaxed text-ink-2">
                  The point is to test whether your bot adjusts its aggression to its bankroll. If
                  capital carried over, a lucky first block would keep a bot rich for the rest of the
                  game and the later blocks would measure early luck rather than strategy. Banking
                  each block as points makes every block a clean, independent test.
                </p>
              </div>
            </div>
            <p class="mt-8 border-l-2 border-flame pl-5 text-sm leading-relaxed text-ink-2" data-fade>
              A bot that goes bankrupt inside a block is out <b class="text-ink">for the remainder of
              that block only</b>. It re-enters at the next boundary with a fresh capital draw.
            </p>
          </div>

          <div data-reveal>
            ${heading("round", "03", "How a round resolves")}
            <ol class="mt-8 space-y-4 text-sm leading-relaxed text-ink-2" data-fade>
              <li><b class="text-ink">1.</b> Every active player is given a value xᵢ, drawn from that
                  block's distribution.</li>
              <li><b class="text-ink">2.</b> Every player submits a bid. Bids may be fractional and
                  must lie in [0, your current capital].</li>
              <li><b class="text-ink">3.</b> The bids are sorted and payoffs are assigned according to
                  the variation in play.</li>
              <li><b class="text-ink">4.</b> new capital = old capital + payoff.</li>
              <li><b class="text-ink">5.</b> A bot whose capital hits zero stops participating for the
                  rest of that block.</li>
              <li><b class="text-ink">6.</b> An illegal bid (above your capital, below zero, NaN,
                  or not returned in time) is automatically set to 0 for that round.</li>
              <li><b class="text-ink">7.</b> In variations 2, 3 and 4, X is the maximum xᵢ over the
                  players <b class="text-ink">active in that round</b>. Bankrupt bots contribute no
                  value, which is why the active count matters: it is the sample size behind X.</li>
            </ol>
            <div class="panel mt-8 p-6 md:p-8" data-fade>
              <h3 class="d4 font-display">Tie-breaking</h3>
              <p class="mt-4 text-sm leading-relaxed text-ink-2">
                In variations 1 and 2, if several players tie for the highest bid, <b class="text-ink">all
                of them win</b> and each receives the winner's payoff in full. Variations 3 and 4
                depend on distinct ranks, so positions there are assigned by sorting descending with
                <b class="text-ink">ties broken uniformly at random</b>. Throughout, b₁ ≥ b₂ ≥ b₃ …
                are the sorted bid values.
              </p>
            </div>
          </div>

          <div data-reveal>
            ${heading("information", "04", "What your bot is told")}
            <p class="mt-8 max-w-2xl text-sm leading-relaxed text-ink-2" data-fade>
              At the start of round t your bot receives exactly the following, and nothing else.
            </p>
            <div class="mt-6" data-fade>
              ${table(
                ["Observation", "Key", ...variations.map((id) => `V${id}`)],
                [...OBSERVATIONS, ...lateObservations()]
                  .filter(([,, ids]) => ids.some((id) => variations.includes(id)))
                  .map(([label, key, ids]) => [
                    dim(label),
                    mono(key),
                    ...variations.map((id) =>
                      ids.includes(id)
                        ? '<span class="text-jade">✓</span>'
                        : '<span class="text-ink-3">-</span>'
                    ),
                  ]),
                { align: [null, null, ...variations.map(() => "right")] }
              )}
            </div>
            <ul class="mt-8 space-y-3 text-sm leading-relaxed text-ink-2" data-fade>
              <li class="flex gap-3"><span class="text-flame">▸</span><span>You are never told
                  m<sub>b</sub>, M<sub>b</sub>, the block index, or when a boundary occurs.</span></li>
              <li class="flex gap-3"><span class="text-flame">▸</span><span>You are never told other
                  players' values, capitals or identities.</span></li>
              <li class="flex gap-3"><span class="text-flame">▸</span><span>In variations 2 to 4 the
                  previous round's realised X is published to everyone: the winner already knows it
                  from their payoff, so publishing it keeps the information set symmetric.</span></li>
              <li class="flex gap-3"><span class="text-flame">▸</span><span>Your bot may keep internal
                  state across rounds, and it is <b class="text-ink">not</b> cleared at a block
                  boundary, which is exactly what lets you detect one.</span></li>
            </ul>
          </div>

          <div data-reveal>
            ${heading("variations", "05", "The variations")}
            <p class="mt-8 max-w-2xl text-sm leading-relaxed text-ink-2" data-fade>
              One file per variation, and you may enter any subset.
              ${
                hidden.length
                  ? `<span class="text-flame">${esc(
                      hidden.map((id) => `V${id}`).join(" and ")
                    )} ${hidden.length === 1 ? "is" : "are"} not released yet.</span>`
                  : ""
              }
            </p>
            <div class="mt-8 grid gap-5 md:grid-cols-2">
              ${[1, 2, 3, 4]
                .map((id, index) => variationPanel(id, index, variations.includes(id)))
                .join("")}
            </div>
            <div class="mt-10">${renderPayoffBench(variations, state)}</div>
          </div>

          <div data-reveal>
            ${heading("scoring", "06", "Scoring and normalisation")}
            <p class="mt-8 max-w-2xl text-sm leading-relaxed text-ink-2" data-fade>
              Raw profit is not comparable across blocks: a block whose hidden maximum is 500 pays
              roughly fifty times a block whose maximum is 10, and starting capitals differ between
              players inside the same block. So profit is normalised twice.
            </p>
            <div class="mt-8 grid gap-px bg-line md:grid-cols-2" data-fade>
              <div class="bg-void p-6 md:p-8">
                <p class="label">Step 1: scale</p>
                <p class="mt-5 font-mono text-sm text-flame">
                  π⁽ᵇ⁾ᵢ = ( C⁽ᵇ'ᵉⁿᵈ⁾ᵢ − C⁽ᵇ'⁰⁾ᵢ ) / M<sub>b</sub>
                </p>
                <p class="mt-5 text-sm leading-relaxed text-ink-2">
                  Profit measured in units of the block's maximum value. A bankrupt bot ends on zero,
                  so its π is −C⁽ᵇ'⁰⁾ / M<sub>b</sub>.
                </p>
              </div>
              <div class="bg-void p-6 md:p-8">
                <p class="label">Step 2: standardise</p>
                <p class="mt-5 font-mono text-sm text-flame">
                  z = clip( (π − μ<sub>b</sub>) / σ<sub>b</sub>, −3, 3 )<br>
                  P = 50 + 15 z ∈ [5, 95]
                </p>
                <p class="mt-5 text-sm leading-relaxed text-ink-2">
                  Taken across the ${esc(groupSize)} players in your group, for that block. If σ is
                  zero everybody gets z = 0. Clipping at three sigma stops one freak block deciding
                  the competition.
                </p>
              </div>
            </div>
            <p class="mt-8 font-mono text-sm text-ink-2" data-fade>
              Iteration score = Σ over the ${esc(blocks)} blocks of P&nbsp;&nbsp;·&nbsp;&nbsp;Total
              score = Σ over iterations.
            </p>
            <p class="mt-6 max-w-2xl text-sm leading-relaxed text-ink-2" data-fade>
              Standardisation is relative, so the board also reports, for every bot: mean normalised
              profit π (is the strategy profitable in absolute terms?), survival rate, worst-block π
              and the spread of π across blocks.
            </p>
            <p class="mt-6" data-fade>
              <a href="/api/docs/scoring.pdf" class="btn-line" target="_blank" rel="noopener">
                The full scoring specification <span>↓</span>
              </a>
            </p>
            <p class="mt-4 max-w-2xl font-mono text-[10px] leading-relaxed text-ink-3" data-fade>
              A PDF: every formula above, every column on the board and what it is for, the
              tournament structure, and how the mock auctions differ from the graded run.
            </p>
          </div>

          <div data-reveal>
            ${heading("tournament", "07", "Tournament structure")}
            <p class="mt-8 max-w-2xl text-sm leading-relaxed text-ink-2" data-fade>
              A single 20-bot arrangement is far too noisy to rank on, who you are grouped with
              matters as much as how you play, particularly in variations 3 and 4 where payoffs are
              transfers between players. Each variation is therefore run over several iterations with
              different random seeds, and the seeds are published afterwards so results are
              reproducible.
            </p>
            <div class="mt-8" data-fade>
              ${table(
                ["Iteration", "Grouping", "What it does"],
                [
                  [mono("1"), dim("random"), dim("All qualifying bots shuffled into groups of 20 with seed S₁.")],
                  [mono("2"), dim("random, fresh seed"), dim("Reshuffled independently: different distributions, capitals and opponents.")],
                  [mono("3"), dim("strength-balanced"), dim("Sorted by cumulative points and dealt in a snake, so every group is roughly equal in average strength.")],
                  [mono("4 to 5"), dim("finals"), dim("The top 20 by cumulative score play two head-to-head iterations on fresh seeds.")],
                ]
              )}
            </div>
            <p class="mt-6 text-sm leading-relaxed text-ink-2" data-fade>
              That is 12 scored blocks in qualification and 8 in the finals, enough for the standard
              error of a bot's mean block score to fall well below the gaps that matter. Final ranking
              is the sum of the two finals iterations, tie-broken by the qualification total. Mock
              auctions run the same machinery at reduced size, with per-block statistics published so
              you can see where your bot broke. This practice board runs
              ${esc(iterations)} ${iterations === 1 ? "iteration" : "iterations"} at a time.
            </p>
          </div>

          <div data-reveal>
            ${heading("worked", "08", "Worked rounds")}
            <p class="mt-8 max-w-2xl text-sm leading-relaxed text-ink-2" data-fade>
              Three bots, 100 capital each. Values 30, 50 and 60, so X = 60; bids 45, 55 and 30. Bot 2
              wins and Bot 1 is the runner-up. The same round settles differently under each
              variation:
            </p>
            <div class="mt-6" data-fade>
              ${table(
                ["Bot", "Strategy", "Value xᵢ", "Bid", ...threeBotColumns.map((id) => `V${id} capital`)],
                SAMPLE_123.map((row) => [
                  `<b>${row.bot}</b>`,
                  dim(row.strategy),
                  mono(row.x),
                  mono(row.bid),
                  ...threeBotColumns.map((id) => mono(lateCaps(row)[id])),
                ])
              )}
            </div>

            ${sampleFour(variations)}
          </div>

          <div data-reveal>
            ${heading("bot", "09", "What your bot looks like")}
            <p class="mt-8 text-sm leading-relaxed text-ink-2" data-fade>
              One file, one class named <code class="font-mono text-flame">Bot</code>, one method that
              returns a number. State you keep on <code class="font-mono text-flame">self</code>
              survives all ${esc(rounds)} rounds and is never cleared at a block boundary.
            </p>
            <pre class="panel mt-6 overflow-x-auto p-6 font-mono text-xs leading-relaxed md:p-8" data-fade><code>class Bot:
    def __init__(self, config):
        <span class="text-ink-3"># called once, before round 1</span>
        self.id = config["player_id"]
        self.seen = []

    def get_bid(self, obs):
        <span class="text-ink-3"># called once per round; return your bid</span>
        self.seen.append(obs["x"])
        <span class="text-ink-3"># obs["capital"] is your legal ceiling</span>
        return min(0.5 * obs["x"], obs["capital"])</code></pre>
            <div class="mt-8 grid gap-px bg-line sm:grid-cols-2" data-fade>
              ${[
                ["Under 1 second per round", "Exceed it and the round is scored as a bid of 0, and your bot may be removed from the auction."],
                ["Under 100 MB of memory", "A bot seen hogging memory is discarded from the auction."],
                ["No files, processes or network", "And no inspecting the simulator's internal state. Any bot doing so is disqualified."],
                ["Any pip library you like", "numpy, pandas, scipy and scikit-learn are available. List whatever you use in your report."],
              ]
                .map(
                  ([title, body]) => `
                <div class="bg-void p-6 md:p-8">
                  <h4 class="d4 font-display">${title}</h4>
                  <p class="mt-3 text-sm leading-relaxed text-ink-2">${body}</p>
                </div>`
                )
                .join("")}
            </div>
          </div>

          <div data-reveal>
            ${heading("submitting", "10", "Submitting")}
            <p class="mt-8 max-w-2xl text-sm leading-relaxed text-ink-2" data-fade>
              A separate file is required for each variation, named
              <code class="font-mono text-flame">ROLLNO_&lt;variation&gt;.py</code>. With what is in
              play right now that means <code class="font-mono text-flame">${esc(filenames)}</code>.
              The roll number must match the one on your smail account. Upload it here and it is
              checked immediately, static policy first, then a short game against the sample bots,
              and either accepted or sent back with a reason. Resubmit as often as you like: the
              newest accepted file per variation is the one that plays.
            </p>
            <p class="mt-6 max-w-2xl text-sm leading-relaxed text-ink-2" data-fade>
              Alongside the code, submit a short report covering, for each variation: the core idea of
              the strategy, how you estimate the hidden distribution, how the bid depends on your
              starting capital, how you detect and react to a block change, and any libraries used.
            </p>
            <div class="mt-8 flex flex-wrap gap-3" data-fade>
              <a href="/submit" data-link class="btn-solid">Submit a bot <span>→</span></a>
              <a href="/public/starter-kit.zip" class="btn-line" download>Download the starter kit</a>
              ${
                formUrl
                  ? `<a href="${esc(formUrl)}" class="btn-quiet" target="_blank" rel="noopener noreferrer">
                       Submission form ↗
                     </a>`
                  : ""
              }
            </div>
          </div>

          <div data-reveal>
            ${heading("metrics", "11", "How you are judged")}
            <ul class="mt-8 space-y-4 text-sm leading-relaxed text-ink-2" data-fade>
              <li class="flex gap-3"><span class="text-flame">▸</span><span>We mainly look at your
                  report and the logical basis for your strategy.</span></li>
              <li class="flex gap-3"><span class="text-flame">▸</span><span><b class="text-ink">Net
                  profit by itself is not a metric.</b> It is read alongside how the strategy adapts
                  to different conditions.</span></li>
              <li class="flex gap-3"><span class="text-flame">▸</span><span>Robustness against
                  different starting capitals, whether aggression genuinely responds to the bankroll
                  rather than being fixed.</span></li>
              <li class="flex gap-3"><span class="text-flame">▸</span><span>Robustness across blocks:
                  consistency of π across the four differently-scaled regimes, and how quickly the bot
                  re-adapts after a boundary.</span></li>
              <li class="flex gap-3"><span class="text-flame">▸</span><span>Survival. Bankruptcies are
                  heavily penalised, since a bankrupt bot forfeits the rest of its block.</span></li>
              <li class="flex gap-3"><span class="text-flame">▸</span><span>Use AI as much as you like
, we are testing the logic behind your strategy, not your typing. Indent properly
                  and comment where it helps us read it.</span></li>
            </ul>

            <p class="label mt-12">Resources</p>
            <div class="mt-5 flex flex-wrap gap-3" data-fade>
              ${RESOURCES.map(
                ([title, href, source]) => `
                <a href="${esc(href)}" target="_blank" rel="noopener noreferrer"
                   class="panel px-5 py-4 transition-colors hover:border-line-2">
                  <span class="block text-sm">${esc(title)}</span>
                  <span class="mt-1 block font-mono text-[10px] uppercase tracking-[0.16em] text-ink-3">
                    ${esc(source)} ↗
                  </span>
                </a>`
              ).join("")}
            </div>
          </div>
        </div>
      </div>`;

    app.querySelectorAll("[data-jump]").forEach((button) =>
      button.addEventListener("click", () => {
        // A plain `#hash` link would push a history entry the SPA router then
        // has to ignore; scrolling directly keeps the two out of each other's way.
        document
          .getElementById(button.dataset.jump)
          ?.scrollIntoView({ behavior: "smooth", block: "start" });
      })
    );

    detachBench();
    detachBench = attachPayoffBench(app);

    if (!firstPaint) revealAll(app);
    firstPaint = false;
  };

  paint();

  // The rules describe whatever is switched on right now, so they follow the
  // same live state everything else does.
  let signature = JSON.stringify([store.state?.variations, store.state?.num_rounds]);
  const unsubscribe = store.subscribe(() => {
    const next = JSON.stringify([store.state?.variations, store.state?.num_rounds]);
    if (next === signature) return;
    signature = next;
    paint();
  });

  return () => {
    detachBench();
    unsubscribe();
  };
}
