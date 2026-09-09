// Landing page: what the game is, when the next showdown fires, who is winning.

import { store } from "../main.js";
import { attachCountdown, renderCountdown } from "../countdown.js";
import { attachPayoffBench, renderPayoffBench } from "../payoff.js";
import { revealAll, revealLines } from "../motion.js";
import { startTape } from "../tape.js";
import {
  VARIATION_META,
  applyBarWidths,
  daysUntil,
  describeInterval,
  enabledVariations,
  esc,
  formatDeadline,
  relativeTime,
  signed,
} from "../ui.js";

const STEPS = [
  {
    n: "01",
    title: "A value only you see",
    body: "Each round every solvent bot privately draws xᵢ from a uniform distribution. Its minimum and maximum are never published, and they change every 500 rounds without warning.",
  },
  {
    n: "02",
    title: "One blind number",
    body: "Everybody bids at once. The legal range is zero to your own capital — over it, negative, NaN or late, and the engine files a zero for you that round.",
  },
  {
    n: "03",
    title: "The ranking pays",
    body: "The highest bid wins. What winning is worth, and whether second place is punished or paid, is the entire difference between the four variations.",
  },
  {
    n: "04",
    title: "Capital is reset",
    body: "At every block boundary your capital is redrawn at 0.5 to 2.5 times the block's hidden maximum. What you finished the block with does not carry over — it is banked as points.",
  },
];

// The variation whose standing is previewed on the front page.
let previewVariation = 0;

// Spelled out rather than built from a count: Tailwind scans this file as text
// and never generates a class it has not literally seen.
const CARD_GRID = {
  1: "md:grid-cols-1 md:max-w-xl",
  2: "md:grid-cols-2",
  3: "md:grid-cols-2 xl:grid-cols-3",
  4: "md:grid-cols-2 xl:grid-cols-4",
};

// --- pieces --------------------------------------------------------------------

function rubric(number, title, trailing = "") {
  return `
    <div class="rubric">
      <span class="font-mono text-[11px] tracking-[0.2em] text-flame">(${number})</span>
      <h2 class="d3 font-display">${title}</h2>
      ${trailing}
    </div>`;
}

function statCell(value, label, digits = 0) {
  return `
    <div class="px-6 py-8 md:px-8 md:py-10">
      <p class="d2 font-display tabular-nums" data-count="${value}" data-count-digits="${digits}">0</p>
      <p class="label mt-4">${esc(label)}</p>
    </div>`;
}

function tickerTape(rows, variations) {
  const live = rows.filter((row) => variations.includes(row.variation));
  const items = live.length
    ? live.slice(0, 24)
    : [{ key: "AWAITING SUBMISSIONS", score: 0, variation: 0 }];

  const cell = (row) => {
    const value = row.score || 0;
    return `
      <span class="flex shrink-0 items-baseline gap-3 border-r border-line px-6 py-3 font-mono text-[11px]">
        <span class="text-ink-3">${row.variation ? `V${row.variation}` : "··"}</span>
        <span>${esc(row.key)}</span>
        <span class="${value >= 0 ? "text-gain" : "text-loss"}">${value ? value.toFixed(1) : "—"}</span>
      </span>`;
  };

  const strip = items.map(cell).join("");
  return `
    <div class="marquee hair-b hair" aria-hidden="true">
      <div class="marquee-track animate-marquee">${strip}</div>
      <div class="marquee-track animate-marquee">${strip}</div>
    </div>`;
}

function variationCard(id, index, counts, live) {
  const meta = VARIATION_META[id];
  const entries = counts?.per_variation?.[id] || 0;

  return `
    <article class="card" data-reveal="${index * 90}">
      <div class="flex items-start justify-between gap-6">
        <span class="font-display text-[3.5rem] leading-none text-line-2" data-fade>${meta.index}</span>
        <span class="tag ${live ? meta.edge : ""} ${live ? meta.ink : ""}">
          ${live ? esc(meta.kind) : "not released"}
        </span>
      </div>

      <h3 class="d4 mt-8 font-display" data-fade>${esc(meta.name)}</h3>
      <p class="mt-3 font-mono text-[11px] ${meta.ink}" data-fade>${esc(meta.short)}</p>
      <p class="mt-5 flex-1 text-sm leading-relaxed text-ink-2" data-fade>${esc(meta.detail)}</p>

      <div class="hair mt-8 flex items-end justify-between pt-5">
        <span>
          <span class="label">Winner takes</span>
          <span class="mt-2 block font-mono text-sm ${meta.ink}">${esc(meta.formula)}</span>
        </span>
        <span class="text-right">
          <span class="label">Entered</span>
          <span class="mt-2 block font-mono text-sm tabular-nums">${entries}</span>
        </span>
      </div>
    </article>`;
}

function standingRows(rows, variation) {
  const top = rows
    .filter((row) => row.variation === variation && !row.disqualified)
    .sort((a, b) => (a.rank || 999) - (b.rank || 999))
    .slice(0, 6);

  if (!top.length) {
    return `
      <div class="px-6 py-20 text-center md:px-8">
        <p class="font-mono text-sm text-ink-3">No showdown has settled for this variation yet.</p>
        <p class="mx-auto mt-3 max-w-sm text-sm text-ink-2">
          The board fills in the moment the first auction finishes. Submit a bot and you are in it.
        </p>
        <a href="/submit" data-link class="btn-line mt-8">Submit a bot <span>→</span></a>
      </div>`;
  }

  const scale = Math.max(...top.map((row) => Math.abs(row.score || 0)), 1);

  return top
    .map(
      (row) => `
        <div class="hair-b flex items-center gap-5 px-6 py-5 last:border-b-0 md:px-8">
          <span class="w-8 shrink-0 font-mono text-sm ${row.rank === 1 ? "text-flame" : "text-ink-3"}">
            ${esc(String(row.rank).padStart(2, "0"))}
          </span>
          <span class="w-36 shrink-0 truncate font-mono text-sm">${esc(row.key)}</span>
          <span class="bar-track hidden sm:block">
            <span class="bar bg-flame" data-bar-width="${Math.round(
              (Math.abs(row.score || 0) / scale) * 100
            )}"></span>
          </span>
          <span class="ml-auto shrink-0 text-right">
            <span class="block font-display text-xl tabular-nums">${(row.score || 0).toFixed(1)}</span>
            <span class="block font-mono text-[10px] text-ink-3">
              π ${signed(row.mean_normalised_profit, 3)}
            </span>
          </span>
        </div>`
    )
    .join("");
}

// The competition calendar (problem statement §2). Everything is IST.
function timeline(state) {
  const deadline = formatDeadline(state.deadline_iso);
  const items = [
    {
      when: "Wed 09/09 · 22:00",
      what: "Orientation session. Variations 1 and 2 released, with the problem statement and starter code.",
      done: true,
    },
    {
      when: "Sat 12/09 · 12:00",
      what: "Deadline for mock submissions of variations 1 and 2. Optional, and strongly recommended.",
    },
    {
      when: "Sat 12/09 · evening",
      what: "Mock auction 1 runs on variations 1 and 2. Results published, and variations 3 and 4 released at the same time.",
      accent: true,
    },
    {
      when: "Mon 14/09 · EOD",
      what: "Deadline for mock submissions of variations 3 and 4. Mock auction 2 runs the same night on all four.",
    },
    {
      when: deadline ? `Wed ${deadline}` : "Wed 16/09 · 23:59",
      what: "Final submission deadline for every variation.",
      final: true,
    },
    {
      when: describeInterval(state.schedule?.interval_minutes),
      what: "This practice board replays the whole field and is rewritten.",
      live: true,
    },
  ];

  return `
    <ol class="hair mt-10">
      ${items
        .map(
          (item, index) => `
        <li class="hair-b flex flex-col gap-2 py-6 md:flex-row md:items-baseline md:gap-10"
            data-reveal="${index * 60}">
          <span class="w-56 shrink-0 font-mono text-[11px] uppercase tracking-[0.16em] ${
            item.live ? "text-flame" : item.final ? "text-ink" : "text-ink-3"
          }" data-fade>
            ${item.live ? '<span class="dot animate-blip mr-2 align-middle"></span>' : ""}${esc(item.when)}
          </span>
          <span class="text-sm leading-relaxed ${item.done ? "text-ink-3" : "text-ink-2"}" data-fade>
            ${esc(item.what)}${item.done ? " ✓" : ""}
          </span>
        </li>`
        )
        .join("")}
    </ol>`;
}

// --- page ----------------------------------------------------------------------

/** Only the things this page draws — a progress tick must not rebuild the DOM. */
function signature() {
  const state = store.state || {};
  return JSON.stringify([
    state.variations,
    state.counts,
    state.num_rounds,
    state.block_size,
    state.group_size,
    state.iterations,
    state.deadline_iso,
    state.schedule?.interval_minutes,
    state.last_showdown?.finished_at,
    previewVariation,
    (store.rows || []).map((row) => [row.variation, row.key, row.rank, row.score]),
  ]);
}

export async function renderHome(app) {
  let detachCountdown = () => {};
  let detachBench = () => {};
  let stopTape = () => {};
  let lastSignature = "";
  let firstPaint = true;

  const paint = () => {
    const state = store.state || {};
    const counts = state.counts || { participants: 0, per_variation: {} };
    const bots = Object.values(counts.per_variation || {}).reduce((a, b) => a + b, 0);
    const variations = enabledVariations(state);
    const hidden = [1, 2, 3, 4].filter((id) => !variations.includes(id));
    const last = state.last_showdown;
    const days = daysUntil(state.deadline_iso);
    const open = state.submissions_open !== false;
    const blocks = state.num_blocks || 4;

    if (!variations.includes(previewVariation)) previewVariation = variations[0] || 0;

    app.innerHTML = `
      <section class="bleed grid items-end gap-14 pb-16 pt-14 lg:grid-cols-[1.25fr_minmax(0,26rem)] lg:pt-20"
               data-reveal>
        <div>
          <span class="tag ${open ? "tag-live" : ""}" data-fade>
            <span class="dot ${open ? "animate-blip" : ""}"></span>
            ${open ? "Submissions open · odd sem 2026" : "Submissions closed"}
          </span>

          <h1 class="d1 mt-8 font-display">
            ${revealLines(["Bid blind.", "Read the", "regime."])}
          </h1>

          <p class="lede mt-10 max-w-xl" data-fade>
            Quant Guild recruitment runs as a sealed-bid auction. Your Python bot plays
            ${esc(state.num_rounds ?? 2000)} rounds against ${esc((state.group_size ?? 20) - 1)}
            others across ${esc(blocks)} blocks — the value distribution and your capital are both
            redrawn at every boundary, and you are never told when one happens.
          </p>

          <div class="mt-10 flex flex-wrap items-center gap-3" data-fade>
            <a href="/submit" data-link class="btn-solid">Submit your bot <span>→</span></a>
            <a href="/rules" data-link class="btn-line">Read the problem</a>
            <a href="/public/starter-kit.zip" class="btn-quiet" download>Starter kit ↓</a>
          </div>

          ${
            days !== null && days >= 0
              ? `<p class="mt-8 font-mono text-[11px] text-ink-3" data-fade>
                   Final deadline ${esc(formatDeadline(state.deadline_iso))} —
                   <span class="text-flame">${
                     days === 0 ? "today" : `${days} day${days === 1 ? "" : "s"} left`
                   }</span>
                 </p>`
              : ""
          }
        </div>

        <div class="panel" data-fade>
          <div class="hair-b flex items-center justify-between px-5 py-3">
            <span class="label">Auction tape</span>
            <span class="label">sample game</span>
          </div>

          <canvas data-tape class="block h-44 w-full" aria-hidden="true"></canvas>

          <div class="hair hair-b flex items-center gap-6 px-5 py-2.5 font-mono text-[10px] text-ink-3">
            <span class="flex items-center gap-2"><span class="h-px w-5 bg-flame"></span>winning bid</span>
            <span class="flex items-center gap-2"><span class="h-px w-5 bg-jade opacity-70"></span>runner-up</span>
          </div>

          <div class="p-5 md:p-6">
            ${renderCountdown({ size: "md" })}
            <p class="hair mt-6 pt-4 font-mono text-[11px] text-ink-3">
              last run ${esc(last ? relativeTime(last.finished_at) : "never")}
              ${last ? `· ${esc(last.games)} games` : ""}
            </p>
          </div>
        </div>
      </section>

      <div class="hair hair-b grid grid-cols-2 divide-x divide-y divide-line md:grid-cols-4 md:divide-y-0">
        ${statCell(counts.participants, "Participants")}
        ${statCell(bots, "Bots in play")}
        ${statCell(state.num_rounds || 2000, "Rounds per game")}
        ${statCell(variations.length, "Variations live")}
      </div>

      ${tickerTape(store.rows || [], variations)}

      <section class="bleed py-20 md:py-28" data-reveal>
        ${rubric("01", "How a round works")}
        <div class="mt-12 grid gap-px bg-line md:grid-cols-2 xl:grid-cols-4">
          ${STEPS.map(
            (step) => `
            <div class="bg-void p-6 md:p-8" data-fade>
              <span class="font-display text-[2.5rem] leading-none text-flame">${step.n}</span>
              <h3 class="d4 mt-6 font-display">${step.title}</h3>
              <p class="mt-4 text-sm leading-relaxed text-ink-2">${step.body}</p>
            </div>`
          ).join("")}
        </div>
      </section>

      <section class="bleed pb-20 md:pb-28" data-reveal>
        ${rubric(
          "02",
          variations.length === 4 ? "Four variations" : "Variations in play",
          `<a href="/rules" data-link class="link shrink-0 font-mono text-[11px] uppercase tracking-[0.16em]">Full rules →</a>`
        )}

        ${
          variations.length
            ? `<div class="mt-12 grid gap-5 ${CARD_GRID[variations.length] || CARD_GRID[4]}">
                 ${variations.map((id, index) => variationCard(id, index, counts, true)).join("")}
               </div>`
            : `<p class="mt-10 text-sm text-ink-2">
                 Every variation is switched off at the moment. Nothing is being played and nothing
                 is being accepted — check back shortly.
               </p>`
        }

        ${
          hidden.length
            ? `<p class="mt-8 border-l-2 border-line-2 pl-5 text-sm leading-relaxed text-ink-3" data-fade>
                 ${esc(hidden.map((id) => `Variation ${id}`).join(" and "))}
                 ${hidden.length === 1 ? "is" : "are"} not released yet — the rules are published when
                 ${hidden.length === 1 ? "it opens" : "they open"}, after mock auction 1. Until then
                 files for ${hidden.length === 1 ? "it" : "them"} are not accepted and
                 ${hidden.length === 1 ? "it does" : "they do"} not appear on the board.
               </p>`
            : ""
        }

        <div class="mt-12">${renderPayoffBench(variations, state)}</div>
      </section>

      <section class="bleed pb-20 md:pb-28" data-reveal>
        ${rubric(
          "03",
          "Where the field stands",
          `<a href="/leaderboard" data-link class="link shrink-0 font-mono text-[11px] uppercase tracking-[0.16em]">Full board →</a>`
        )}

        <p class="mt-6 max-w-2xl text-sm leading-relaxed text-ink-2" data-fade>
          The figure is the standardised score: each block's profit is measured in units of that
          block's hidden maximum, then scored against the other nineteen bots in the group. Raw
          profit is reported next to it, but it is not what ranks you.
        </p>

        ${
          variations.length > 1
            ? `<div class="mt-8 flex flex-wrap gap-2" data-fade>
                 ${variations
                   .map(
                     (id) => `
                   <button data-preview="${id}"
                           class="${id === previewVariation ? "btn-solid" : "btn-line"} px-4 py-2">
                     ${VARIATION_META[id].index} ${esc(VARIATION_META[id].name)}
                   </button>`
                   )
                   .join("")}
               </div>`
            : ""
        }

        <div class="panel mt-8">
          ${
            previewVariation
              ? standingRows(store.rows || [], previewVariation)
              : `<p class="px-8 py-16 text-center font-mono text-sm text-ink-3">Nothing in play.</p>`
          }
        </div>
      </section>

      <section class="bleed pb-20 md:pb-28" data-reveal>
        ${rubric("04", "Calendar")}
        ${timeline(state)}
      </section>

      <section class="invert-band">
        <div class="bleed flex flex-col gap-10 py-20 md:flex-row md:items-end md:justify-between">
          <h2 class="d2 max-w-2xl font-display">Ship something<br>and find out.</h2>
          <div class="flex flex-wrap gap-3">
            <a href="/submit" data-link
               class="btn inline-flex bg-void px-6 py-3 font-mono text-[11px] uppercase tracking-[0.18em] text-ink">
              Submit your bot →
            </a>
            <a href="/public/starter-kit.zip" download
               class="btn inline-flex border border-current px-6 py-3 font-mono text-[11px] uppercase tracking-[0.18em] opacity-70 hover:opacity-100">
              Starter kit ↓
            </a>
          </div>
        </div>
      </section>`;

    // Deferred DOM work: bar widths (a `style` attribute in the markup would be
    // dropped by the Content-Security-Policy), listeners, canvas, clock.
    applyBarWidths(app);

    app.querySelectorAll("[data-preview]").forEach((button) =>
      button.addEventListener("click", () => {
        previewVariation = Number(button.dataset.preview);
        lastSignature = "";
        repaint();
      })
    );

    detachCountdown = attachCountdown(app, () => store.schedule);
    detachBench = attachPayoffBench(app);
    stopTape = startTape(app.querySelector("[data-tape]"));

    // The router observes the first render; anything built after that has to
    // show itself, or it would sit in its pre-reveal state forever.
    if (!firstPaint) revealAll(app);
    firstPaint = false;
  };

  const repaint = () => {
    const next = signature();
    if (next === lastSignature) return;
    lastSignature = next;

    detachCountdown();
    detachBench();
    stopTape();
    paint();
  };

  repaint();

  let scheduled = null;
  const unsubscribe = store.subscribe(() => {
    clearTimeout(scheduled);
    scheduled = setTimeout(repaint, 300);
  });

  return () => {
    clearTimeout(scheduled);
    detachCountdown();
    detachBench();
    stopTape();
    unsubscribe();
  };
}
