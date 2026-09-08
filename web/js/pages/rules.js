// The problem statement, rendered as a page rather than a PDF nobody opens.

import { store } from "../main.js";
import { VARIATION_META, esc } from "../ui.js";

const CONFIG_KEYS = [
  ["player_id", "int", "Your index in the group, stable for the whole game"],
  ["variation", "int", "1, 2 or 3"],
  ["num_players", "int", "Players at the start, before any elimination"],
  ["num_rounds", "int", "2000"],
  ["starting_capital", "float", "What you begin with — it is varied between runs"],
  ["max_bid", "float", "Legal bids lie in [0, max_bid]"],
];

const OBS_KEYS = [
  ["round", "int", "0-indexed round number"],
  ["x", "float", "Your private value this round. Nobody else's."],
  ["capital", "float", "What you have right now"],
  ["num_players", "int", "Players still active this round"],
  ["max_bid", "float", "Legal bid ceiling"],
  ["highest_bid_last_100", "float", "Highest single bid in the last ≤100 rounds"],
  ["second_highest_bid_last_100", "float", "Second-highest over the same window"],
  ["highest_bids", "list[float]", "Per-round highest bid, oldest → newest"],
  ["second_highest_bids", "list[float]", "Per-round second-highest, aligned with the above"],
];

const SAMPLE_RUN = [
  ["Bot 1", "bids x + 15", 30, 45, "100", "100", "97.50"],
  ["Bot 2", "bids x + 5", 50, 55, "95", "105", "105"],
  ["Bot 3", "bids 0.5 x", 60, 30, "100", "100", "100"],
];

function table(headers, rows) {
  return `
    <div class="panel overflow-x-auto">
      <table class="w-full min-w-[38rem] text-left text-sm">
        <thead class="border-b border-line bg-surface-2/50">
          <tr>${headers
            .map(
              (h) =>
                `<th class="px-4 py-2.5 font-mono text-[10px] uppercase tracking-[0.16em] text-ink-faint">${h}</th>`
            )
            .join("")}</tr>
        </thead>
        <tbody class="divide-y divide-line/60">
          ${rows
            .map(
              (row) =>
                `<tr class="transition-colors hover:bg-surface-2/40">${row
                  .map((cell) => `<td class="px-4 py-2.5 align-top">${cell}</td>`)
                  .join("")}</tr>`
            )
            .join("")}
        </tbody>
      </table>
    </div>`;
}

const mono = (text) => `<code class="font-mono text-xs text-gold">${esc(text)}</code>`;
const dim = (text) => `<span class="text-ink-dim">${esc(text)}</span>`;

function variationPanel(id) {
  const meta = VARIATION_META[id];
  const rules = {
    1: [
      "The winner's payoff is <b>xᵢ − bid</b>, using the winner's own value.",
      "Everyone else scores zero for the round.",
      "Bidding above your own value is a guaranteed loss when you win.",
    ],
    2: [
      "The winner's payoff is <b>X − bid</b>, where X is the largest value drawn by <i>anyone</i> that round.",
      "You never see X. You only see your own xᵢ.",
      "The prize is identical for every bot, so this is a pure bidding contest.",
    ],
    3: [
      "The winner's payoff is <b>X − bid</b>, exactly as in variation 2.",
      "The second-highest bidder pays <b>−0.5 × (X − bid)</b>.",
      "If X − bid is negative the runner-up pays nothing — the penalty never becomes a reward.",
    ],
  }[id];

  return `
    <article data-reveal="${id * 60}" class="panel p-6">
      <div class="flex items-center gap-3">
        <span class="chip ${meta.ring} ${meta.accent}">Variation ${id}</span>
        <h3 class="font-heading text-lg font-bold">${meta.name}</h3>
      </div>
      <ul class="mt-4 space-y-2 text-sm leading-relaxed text-ink-dim">
        ${rules.map((rule) => `<li class="flex gap-2"><span class="${meta.accent}">▸</span><span>${rule}</span></li>`).join("")}
      </ul>
      <div class="mt-5 rounded-xl border border-line bg-void/60 px-4 py-3">
        <p class="font-mono text-[10px] uppercase tracking-[0.2em] text-ink-faint">Winner payoff</p>
        <p class="mt-1 font-mono text-base ${meta.accent}">${meta.formula}</p>
      </div>
    </article>`;
}

export async function renderRules(app) {
  const state = store.state || {};
  const maxBid = state.max_bid ?? 100;
  const capitals = (state.starting_capitals || [100]).join(", ");

  app.innerHTML = `
    <section class="mx-auto max-w-5xl px-5 py-14">
      <span class="chip border-gold/40 text-gold">Problem statement</span>
      <h1 class="mt-4 font-heading text-4xl font-bold md:text-5xl">The rules of the auction</h1>
      <p class="mt-4 max-w-2xl text-base leading-relaxed text-ink-dim">
        Every participant writes a bot that plays a repeated sealed-bid auction. The bot with the
        highest bid wins the round; what winning is <i>worth</i> is what separates the three
        variations. Below is everything the engine actually does.
      </p>

      <div class="mt-6 flex flex-wrap gap-2">
        <span class="chip">${esc(state.num_rounds ?? 2000)} rounds</span>
        <span class="chip">groups of ${esc(state.group_size ?? 20)}</span>
        <span class="chip">max bid ${esc(maxBid)}</span>
        <span class="chip">starting capital ${esc(capitals)}</span>
        <span class="chip">1 s / round · 100 MB</span>
      </div>

      <div class="rule-gold my-12"></div>

      <h2 class="font-heading text-2xl font-bold">The game</h2>
      <ol class="mt-5 space-y-3 text-sm leading-relaxed text-ink-dim">
        <li><b class="text-ink">Values.</b> Each round every active bot privately draws xᵢ from a
            uniform distribution. Draws are independent — your value tells you nothing about anyone else's.</li>
        <li><b class="text-ink">Hidden regimes.</b> The distribution's minimum and maximum are never
            revealed, and they change every 500 rounds. A strategy tuned to the first block will
            be wrong for the second.</li>
        <li><b class="text-ink">Bidding.</b> Submit one number in [0, ${esc(maxBid)}]. Fractional bids are fine.</li>
        <li><b class="text-ink">Winning.</b> Highest bid wins. If several bots tie at the top,
            <i>all</i> of them win and each collects the full payoff.</li>
        <li><b class="text-ink">Capital.</b> new capital = old capital + payoff. Payoffs can be negative.</li>
        <li><b class="text-ink">Elimination.</b> Run out of capital and you take no further part in the game.</li>
        <li><b class="text-ink">Illegal bids.</b> A bid above your available capital is silently replaced with 0
            for that round. NaN, infinity, negatives and non-numbers are treated the same way.</li>
      </ol>

      <div class="rule-gold my-12"></div>

      <h2 class="font-heading text-2xl font-bold">Three variations</h2>
      <p class="mt-2 text-sm text-ink-dim">One file per variation. You may enter any subset.</p>
      <div class="mt-6 grid gap-4 md:grid-cols-3">${[1, 2, 3].map(variationPanel).join("")}</div>

      <div class="rule-gold my-12"></div>

      <h2 class="font-heading text-2xl font-bold">A worked round</h2>
      <p class="mt-2 max-w-2xl text-sm text-ink-dim">
        Three bots, 100 capital each. Values 30, 50 and 60; bids 45, 55 and 30. Bot 2 wins,
        Bot 1 is the runner-up. The same round scores differently under each variation:
      </p>
      <div class="mt-6">
        ${table(
          ["Bot", "Strategy", "Value xᵢ", "Bid", "V1 capital", "V2 capital", "V3 capital"],
          SAMPLE_RUN.map(([bot, strategy, x, bid, v1, v2, v3]) => [
            `<b class="text-ink">${bot}</b>`,
            dim(strategy),
            mono(x),
            mono(bid),
            mono(v1),
            mono(v2),
            mono(v3),
          ])
        )}
      </div>

      <div class="rule-gold my-12"></div>

      <h2 class="font-heading text-2xl font-bold">What your bot looks like</h2>
      <p class="mt-2 text-sm text-ink-dim">
        One file, one class named <code class="font-mono text-gold">Bot</code>, one method that returns a number.
      </p>
      <pre class="panel mt-5 overflow-x-auto p-5 font-mono text-xs leading-relaxed text-ink-dim"><code>class Bot:
    def __init__(self, config):
        <span class="text-ink-faint"># called once, before round 0</span>
        self.id = config["player_id"]

    def get_bid(self, obs):
        <span class="text-ink-faint"># called once per round; return your bid</span>
        x = obs["x"]
        return min(0.5 * x, obs["max_bid"], obs["capital"])</code></pre>

      <h3 class="mt-10 font-heading text-lg font-bold">config — passed to <code class="font-mono text-gold">__init__</code></h3>
      <div class="mt-4">
        ${table(
          ["Key", "Type", "Meaning"],
          CONFIG_KEYS.map(([key, type, meaning]) => [mono(key), dim(type), dim(meaning)])
        )}
      </div>

      <h3 class="mt-10 font-heading text-lg font-bold">obs — passed to <code class="font-mono text-gold">get_bid</code> every round</h3>
      <div class="mt-4">
        ${table(
          ["Key", "Type", "Meaning"],
          OBS_KEYS.map(([key, type, meaning]) => [mono(key), dim(type), dim(meaning)])
        )}
      </div>

      <div class="rule-gold my-12"></div>

      <h2 class="font-heading text-2xl font-bold">Limits your bot must respect</h2>
      <div class="mt-5 grid gap-4 sm:grid-cols-2">
        ${[
          ["Under 1 second per round", "Exceed it and the round is scored as a bid of 0 — and your bot is out of that game."],
          ["Under 100 MB of memory", "The sandbox enforces a hard ceiling; allocate past it and the process dies."],
          ["No network, no files, no processes", "Submissions are statically checked and then run in an isolated sandbox with no network and a read-only filesystem."],
          ["Any pip library you like", "numpy, pandas, scipy and scikit-learn are available. List whatever you use in your report."],
        ]
          .map(
            ([title, body]) => `
            <div class="panel p-5">
              <h4 class="font-heading text-sm font-bold text-ink">${title}</h4>
              <p class="mt-1.5 text-sm leading-relaxed text-ink-dim">${body}</p>
            </div>`
          )
          .join("")}
      </div>

      <div class="rule-gold my-12"></div>

      <h2 class="font-heading text-2xl font-bold">Submitting</h2>
      <p class="mt-3 text-sm leading-relaxed text-ink-dim">
        Name each file <code class="font-mono text-gold">ROLLNO_&lt;variation&gt;.py</code> — so
        <code class="font-mono text-gold">ME24B152_1.py</code> for variation 1. The roll number
        must match the one on your smail account. Upload it on the submit page; it is checked
        immediately against the sample bots and either accepted or sent back with a reason.
        Resubmit as often as you like — the newest accepted file per variation is the one that plays.
      </p>
      <div class="mt-7 flex flex-wrap gap-3">
        <a href="/submit" data-link class="btn-gold">Submit a bot</a>
        <a href="/public/starter-kit.zip" class="btn-ghost" download>Download the starter kit</a>
      </div>
    </section>`;
}
