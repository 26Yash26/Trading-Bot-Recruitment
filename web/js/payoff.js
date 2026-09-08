// The payoff bench: four sliders, and what the same round would have paid *you*
// under each variation currently in play.
//
// This is the one place on the site where the rules stop being prose. The
// arithmetic is the arithmetic in `src/auction/variations.py`, so the two are
// worth keeping in step if the engine ever changes.
//
// The model is deliberately two-sided: you bid b, your best rival bids r, and
// everyone else is below both. That is the smallest setup in which variation 4
// says anything interesting, because V4 pays rank one and rank two differently.

import { VARIATION_META, clamp, esc, signed } from "./ui.js";

// Kept outside the render so a repaint — a new leaderboard, a settings change —
// does not throw away the reader's sliders.
const bench = { x: 62, bid: 48, rival: 42, max: 70 };

const SCALE = 100;

function slider(key, label, note, value) {
  return `
    <label class="block">
      <span class="flex items-baseline justify-between gap-3">
        <span class="label">${esc(label)}</span>
        <span class="font-mono text-sm tabular-nums" data-lab-out="${key}">${value.toFixed(1)}</span>
      </span>
      <input type="range" class="slider mt-4" data-lab="${key}"
             min="0" max="${SCALE}" step="0.5" value="${value}" aria-label="${esc(label)}">
      <span class="mt-3 block font-mono text-[11px] leading-relaxed text-ink-3">${esc(note)}</span>
    </label>`;
}

export function renderPayoffBench(variations, _state) {
  Object.keys(bench).forEach((key) => {
    bench[key] = clamp(bench[key], 0, SCALE);
  });

  if (!variations.length) {
    return `
      <div class="panel p-8">
        <p class="text-sm text-ink-2">No variation is in play, so there is nothing to price.</p>
      </div>`;
  }

  return `
    <div class="panel" data-bench>
      <div class="hair-b flex flex-wrap items-baseline justify-between gap-3 p-6 md:p-8">
        <h3 class="d4 font-display">Price a round yourself</h3>
        <span class="tag">Interactive</span>
      </div>

      <div class="grid lg:grid-cols-[minmax(0,22rem)_1fr]">
        <div class="hair-b space-y-8 p-6 md:p-8 lg:border-b-0 lg:border-r lg:border-r-line">
          ${slider("x", "Your value  xᵢ", "The draw only you can see.", bench.x)}
          ${slider("bid", "Your bid  b", "One number, submitted blind.", bench.bid)}
          ${slider("rival", "Best rival bid  r", "The strongest bid against you.", bench.rival)}
          ${slider("max", "Field max  X", "The best draw anyone got. Never below your own.", bench.max)}
        </div>

        <div class="divide-y divide-line" data-bench-rows>
          ${variations.map(benchRow).join("")}
          <p class="p-6 font-mono text-[11px] leading-relaxed text-ink-3 md:p-8">
            A bid above your own capital is filed as a zero. In variations 1 and 2 tied top bids
            all win in full; in 3 and 4 ties are broken uniformly at random.
          </p>
        </div>
      </div>
    </div>`;
}

function benchRow(id) {
  const meta = VARIATION_META[id];
  return `
    <div class="p-6 md:p-8" data-bench-row="${id}">
      <div class="flex items-baseline justify-between gap-3">
        <span class="font-mono text-[11px] uppercase tracking-[0.18em] ${meta.ink}">
          ${meta.index} · ${esc(meta.name)}
        </span>
        <span class="font-mono text-[11px] text-ink-3" data-bench-formula="${id}"></span>
      </div>

      <div class="mt-5 flex items-center gap-5">
        <span class="w-28 shrink-0 font-display text-3xl tabular-nums" data-bench-value="${id}">+0.00</span>
        <span class="bar-track"><span class="bar" data-bench-bar="${id}"></span></span>
      </div>

      <p class="mt-3 font-mono text-[11px] leading-relaxed text-ink-3" data-bench-note="${id}"></p>
    </div>`;
}

/**
 * Your payoff, given the bench state. Returns the number plus a sentence
 * explaining where it came from — the sentence is the point of the exercise.
 */
function evaluate(id, { x, bid, rival, max }) {
  const won = bid >= rival;
  const b1 = Math.max(bid, rival);
  const b2 = Math.min(bid, rival);
  const surplus = max - b1;

  if (id === 1) {
    return won
      ? { value: x - bid, formula: `${x.toFixed(1)} − ${bid.toFixed(1)}`,
          note: x - bid >= 0 ? "you kept your own surplus" : "you paid more than it was worth to you" }
      : { value: 0, formula: "—", note: "rank 2 scores nothing in this variation" };
  }

  if (id === 2) {
    return won
      ? { value: surplus, formula: `${max.toFixed(1)} − ${bid.toFixed(1)}`,
          note: surplus >= 0 ? "you kept the common surplus" : "you outbid the field maximum" }
      : { value: 0, formula: "—", note: "rank 2 scores nothing in this variation" };
  }

  if (id === 3) {
    if (won) {
      return { value: surplus, formula: `${max.toFixed(1)} − ${bid.toFixed(1)}`,
               note: `the runner-up pays ${signed(-0.5 * Math.max(0, surplus))}` };
    }
    const penalty = -0.5 * Math.max(0, surplus);
    return { value: penalty, formula: `−0.5 × (${max.toFixed(1)} − ${b1.toFixed(1)})`,
             note: penalty === 0
               ? "the winner overpaid, so second place pays nothing"
               : "second place funds half the winner's surplus" };
  }

  // Variation 4.
  if (b1 > max) {
    return won
      ? { value: max - bid, formula: `${max.toFixed(1)} − ${bid.toFixed(1)}`,
          note: "b₁ > X, so the winner eats the loss alone and no penalties are collected" }
      : { value: 0, formula: "—", note: "b₁ > X, so nobody but the winner is touched" };
  }
  return won
    ? { value: max - b2, formula: `${max.toFixed(1)} − ${b2.toFixed(1)}`,
        note: "rank 1 pays the second price, funded by ranks 3–5" }
    : { value: max - b1, formula: `${max.toFixed(1)} − ${b1.toFixed(1)}`,
        note: "rank 2 is paid too — it is rank 3 that you do not want to be" };
}

/** Wire a rendered bench. Returns a teardown function. */
export function attachPayoffBench(root) {
  const host = root.querySelector("[data-bench]");
  if (!host) return () => {};

  const inputs = [...host.querySelectorAll("[data-lab]")];

  const compute = () => {
    // X is the maximum over every active player, so it can never sit below your
    // own draw; the slider is allowed to go there, and is corrected here.
    const state = { ...bench, max: Math.max(bench.max, bench.x) };

    const rows = [...host.querySelectorAll("[data-bench-row]")];
    const results = rows.map((row) => evaluate(Number(row.dataset.benchRow), state));
    const scale = Math.max(1, ...results.map((r) => Math.abs(r.value)));

    rows.forEach((row, index) => {
      const id = Number(row.dataset.benchRow);
      const { value, formula, note } = results[index];
      const positive = value >= 0;

      const valueEl = host.querySelector(`[data-bench-value="${id}"]`);
      valueEl.textContent = signed(value);
      valueEl.className = `w-28 shrink-0 font-display text-3xl tabular-nums ${
        value === 0 ? "text-ink-3" : positive ? "text-gain" : "text-loss"
      }`;

      const bar = host.querySelector(`[data-bench-bar="${id}"]`);
      bar.className = `bar ${value === 0 ? "bg-line-2" : positive ? "bg-gain" : "bg-loss"}`;
      bar.style.width = `${clamp((Math.abs(value) / scale) * 100, 1.5, 100)}%`;

      host.querySelector(`[data-bench-formula="${id}"]`).textContent = formula;
      host.querySelector(`[data-bench-note="${id}"]`).textContent = note;
    });

    const rank = bench.bid >= bench.rival ? "you are rank 1" : "you are rank 2";
    const maxOut = host.querySelector('[data-lab-out="max"]');
    if (maxOut) {
      maxOut.textContent = state.max.toFixed(1);
      maxOut.className = `font-mono text-sm tabular-nums ${
        bench.max < bench.x ? "text-flame" : ""
      }`;
    }
    const rivalOut = host.querySelector('[data-lab-out="rival"]');
    if (rivalOut) rivalOut.title = rank;
  };

  const onInput = (event) => {
    const key = event.target.dataset.lab;
    bench[key] = Number(event.target.value) || 0;
    const out = host.querySelector(`[data-lab-out="${key}"]`);
    if (out && key !== "max") out.textContent = bench[key].toFixed(1);
    compute();
  };

  inputs.forEach((input) => input.addEventListener("input", onInput));
  compute();

  return () => inputs.forEach((input) => input.removeEventListener("input", onInput));
}
