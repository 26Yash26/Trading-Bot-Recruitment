// The live board. Variation tabs, search, sorting, expandable rows.

import { store } from "../main.js";
import { attachCountdown, renderCountdown } from "../countdown.js";
import { revealAll, revealLines } from "../motion.js";
import {
  VARIATION_META,
  applyBarWidths,
  enabledVariations,
  esc,
  money,
  relativeTime,
  signed,
} from "../ui.js";

let activeVariation = 0;
let query = "";
let sortKey = "rank";
const expanded = new Set();
const lastRanks = new Map(); // "V:key" -> rank, for the movement arrows

const SORTS = [
  ["rank", "Rank"],
  ["score", "Score"],
  ["profit", "Mean π"],
  ["spread", "Consistency"],
  ["survival", "Survival"],
];

function comparator(key) {
  if (key === "score") return (a, b) => (b.score || 0) - (a.score || 0);
  if (key === "profit")
    return (a, b) => (b.mean_normalised_profit || 0) - (a.mean_normalised_profit || 0);
  if (key === "spread")
    return (a, b) => (a.normalised_profit_spread || 0) - (b.normalised_profit_spread || 0);
  if (key === "survival") return (a, b) => (b.survival_rate || 0) - (a.survival_rate || 0);
  return (a, b) => (a.rank || 9999) - (b.rank || 9999);
}

function movement(row) {
  const id = `${row.variation}:${row.key}`;
  const previous = lastRanks.get(id);
  lastRanks.set(id, row.rank);
  if (previous === undefined || previous === row.rank) return "";

  const up = row.rank < previous;
  return `<span class="ml-2 font-mono text-[10px] ${up ? "text-gain" : "text-loss"}">
            ${up ? "▲" : "▼"}${Math.abs(previous - row.rank)}
          </span>`;
}

function rankCell(row) {
  if (row.disqualified) {
    return `<span class="grid h-9 w-9 shrink-0 place-items-center border border-loss text-sm text-loss">✕</span>`;
  }
  const style =
    row.rank === 1
      ? "border-flame text-flame"
      : row.rank <= 3
        ? "border-line-2 text-ink"
        : "border-line text-ink-3";
  return `<span class="grid h-9 w-9 shrink-0 place-items-center border font-mono text-xs ${style}">
            ${esc(String(row.rank).padStart(2, "0"))}
          </span>`;
}

function detailGrid(row) {
  const cells = [
    ["Total score", (row.score || 0).toFixed(1)],
    ["Mean block score", (row.mean_block_points || 0).toFixed(1)],
    ["Iterations played", row.games],
    ["Blocks scored", row.blocks],
    ["Mean normalised profit π", signed(row.mean_normalised_profit, 3)],
    ["Worst block π", signed(row.worst_normalised_profit, 3)],
    ["Spread of π", money(row.normalised_profit_spread, 3)],
    ["Survival rate", `${Math.round((row.survival_rate ?? 0) * 100)}%`],
    ["Mean raw profit", signed(row.mean_net_profit)],
    ["Mean final capital", money(row.mean_final_capital)],
    ["Rounds won", row.wins],
    ["Errors / timeouts", `${row.errors} / ${row.timeouts}`],
  ];

  return `
    <div class="hair bg-void-3 px-5 py-6 md:px-8">
      <dl class="grid grid-cols-2 gap-x-8 gap-y-5 md:grid-cols-4">
        ${cells
          .map(
            ([label, value]) => `
          <div>
            <dt class="label">${label}</dt>
            <dd class="mt-2 font-mono text-sm">${esc(value)}</dd>
          </div>`
          )
          .join("")}
      </dl>
      ${
        row.disqualified
          ? `<p class="mt-6 border-l-2 border-loss px-4 py-2 font-mono text-xs text-loss">
               Disqualified — ${esc(row.reason || "sandbox violation")}
             </p>`
          : ""
      }
    </div>`;
}

function boardRow(row, scale, mine) {
  const isOpen = expanded.has(`${row.variation}:${row.key}`);
  const score = row.score || 0;
  const profit = row.mean_normalised_profit || 0;

  return `
    <div class="hair-b last:border-b-0 ${mine ? "bg-void-3" : ""}">
      <button class="flex w-full items-center gap-5 px-5 py-4 text-left transition-colors hover:bg-void-3 md:px-8"
              data-toggle="${esc(row.key)}" aria-expanded="${isOpen}">
        ${rankCell(row)}

        <span class="min-w-0 flex-1">
          <span class="flex items-center font-mono text-sm">
            ${esc(row.key)}${movement(row)}
            ${mine ? '<span class="tag ml-3 py-0">you</span>' : ""}
          </span>
          ${row.name ? `<span class="mt-1 block truncate text-xs text-ink-3">${esc(row.name)}</span>` : ""}
        </span>

        <span class="hidden w-44 shrink-0 lg:block">
          <span class="bar-track">
            <span class="bar ${row.disqualified ? "bg-line-2" : "bg-flame"}"
                  data-bar-width="${Math.round((Math.abs(score) / scale) * 100)}"></span>
          </span>
        </span>

        <span class="hidden w-28 shrink-0 text-right sm:block">
          <span class="block font-mono text-[11px] ${profit >= 0 ? "text-gain" : "text-loss"}">
            π ${signed(profit, 3)}
          </span>
          <span class="block font-mono text-[11px] text-ink-3">
            ${Math.round((row.survival_rate ?? 0) * 100)}% alive
          </span>
        </span>

        <span class="w-24 shrink-0 text-right font-display text-xl tabular-nums
                     ${row.disqualified ? "text-ink-3 line-through" : ""}">
          ${score.toFixed(1)}
        </span>

        <span class="shrink-0 font-mono text-ink-3 transition-transform ${isOpen ? "rotate-90" : ""}">›</span>
      </button>
      ${isOpen ? detailGrid(row) : ""}
    </div>`;
}

function emptyBoard(variation, filtered) {
  if (filtered) {
    return `
      <div class="px-8 py-20 text-center">
        <p class="font-mono text-sm text-ink-3">No bot matches “${esc(query)}”.</p>
      </div>`;
  }
  return `
    <div class="px-8 py-24 text-center">
      <p class="font-mono text-sm text-ink-3">Nothing on the board for variation ${esc(variation)} yet.</p>
      <p class="mx-auto mt-3 max-w-sm text-sm text-ink-2">
        Bots appear here once the next showdown finishes.
      </p>
      <a href="/submit" data-link class="btn-line mt-8">Submit a bot <span>→</span></a>
    </div>`;
}

export async function renderLeaderboard(app) {
  let detach = () => {};
  let firstPaint = true;

  const paint = () => {
    const state = store.state || {};
    const variations = enabledVariations(state);
    if (!variations.includes(activeVariation)) activeVariation = variations[0] || 0;

    const schedule = store.schedule;
    const live = Boolean(schedule.running);
    const myRoll = (store.me.roll || "").toUpperCase();

    const all = (store.rows || []).filter((row) => row.variation === activeVariation);
    const needle = query.trim().toLowerCase();
    const rows = (needle
      ? all.filter(
          (row) =>
            String(row.key).toLowerCase().includes(needle) ||
            String(row.name || "").toLowerCase().includes(needle)
        )
      : [...all]
    ).sort(comparator(sortKey));

    const scale = Math.max(...all.map((row) => Math.abs(row.score || 0)), 1);

    app.innerHTML = `
      <section class="bleed grid gap-12 py-14 lg:grid-cols-[1fr_minmax(0,20rem)]" data-reveal>
        <div>
          <span class="tag ${live ? "tag-live" : ""}" data-fade>
            <span class="dot ${live ? "animate-blip" : ""}"></span>
            ${live ? "Showdown in progress" : "Board settled"}
          </span>
          <h1 class="d1 mt-8 font-display">${revealLines(["Leader", "board"])}</h1>
          <p class="lede mt-8 max-w-xl" data-fade>
            Every bot plays ${esc(state.iterations ?? 3)}
            ${(state.iterations ?? 3) === 1 ? "iteration" : "iterations"} of
            ${esc(state.num_rounds ?? 2000)} rounds in randomised groups of
            ${esc(state.group_size ?? 20)}. Each of the ${esc(state.num_blocks ?? 4)} blocks is
            scored against the rest of the group and the scores are summed — so who you were drawn
            against matters far less than how you played.
          </p>
          <p class="mt-6 font-mono text-[11px] text-ink-3" data-fade>
            last showdown ${esc(
              state.last_showdown ? relativeTime(state.last_showdown.finished_at) : "never"
            )}${state.last_showdown ? ` · ${esc(state.last_showdown.games)} games played` : ""}
          </p>
        </div>

        <div class="panel self-start p-6" data-fade>${renderCountdown({ size: "sm" })}</div>
      </section>

      ${
        live && schedule.progress_total
          ? `<div class="bleed pb-8">
               <div class="panel p-5">
                 <div class="flex items-center justify-between font-mono text-[11px]">
                   <span class="text-flame">playing games…</span>
                   <span>${esc(schedule.progress_done)} / ${esc(schedule.progress_total)}</span>
                 </div>
                 <div class="bar-track mt-3">
                   <div class="bar bg-flame" data-bar-width="${Math.round(
                     (schedule.progress_done / schedule.progress_total) * 100
                   )}"></div>
                 </div>
               </div>
             </div>`
          : ""
      }

      ${
        variations.length
          ? `
      <div class="bleed">
        <div class="hair flex flex-wrap items-end justify-between gap-5 pt-8">
          <div class="flex flex-wrap gap-2" role="tablist" aria-label="Variation">
            ${variations
              .map((id) => {
                const meta = VARIATION_META[id];
                const active = id === activeVariation;
                const count = (store.rows || []).filter((r) => r.variation === id).length;
                return `
                  <button role="tab" aria-selected="${active}" data-variation="${id}"
                          class="${active ? "btn-solid" : "btn-line"} px-4 py-2.5">
                    ${meta.index} ${esc(meta.name)}
                    <span class="ml-1 text-[10px] opacity-60">${count}</span>
                  </button>`;
              })
              .join("")}
          </div>

          <label class="relative w-full sm:w-72">
            <span class="sr-only">Search the board</span>
            <input class="field pl-8" type="search" data-search placeholder="Filter by roll or name"
                   value="${esc(query)}">
            <span class="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-3">⌕</span>
          </label>
        </div>

        <div class="mt-6 flex flex-wrap items-center gap-1">
          <span class="label mr-3">Sort by</span>
          ${SORTS.map(
            ([key, label]) => `
            <button data-sort="${key}"
                    class="border-b-2 px-3 py-1.5 font-mono text-[11px] transition-colors ${
                      sortKey === key
                        ? "border-flame text-ink"
                        : "border-transparent text-ink-3 hover:text-ink"
                    }">${label}</button>`
          ).join("")}
        </div>

        <div class="panel mt-6">
          <div class="hair-b flex items-center gap-5 bg-void-3 px-5 py-3 md:px-8">
            <span class="label w-9">#</span>
            <span class="label flex-1">Bot</span>
            <span class="label hidden w-44 lg:block">Relative</span>
            <span class="label hidden w-28 text-right sm:block">Profit · alive</span>
            <span class="label w-24 text-right">Score</span>
            <span class="w-3"></span>
          </div>
          ${
            rows.length
              ? rows
                  .map((row) => boardRow(row, scale, myRoll && row.key.toUpperCase() === myRoll))
                  .join("")
              : emptyBoard(activeVariation, Boolean(needle) && all.length > 0)
          }
        </div>
      </div>`
          : `<div class="bleed">
               <div class="panel px-8 py-24 text-center">
                 <p class="font-mono text-sm text-ink-3">No variation is currently in play.</p>
                 <p class="mx-auto mt-3 max-w-sm text-sm text-ink-2">
                   The organisers have switched every variation off. The board comes back when one
                   is switched on again.
                 </p>
               </div>
             </div>`
      }`;

    applyBarWidths(app);

    app.querySelectorAll("[data-variation]").forEach((button) =>
      button.addEventListener("click", () => {
        activeVariation = Number(button.dataset.variation);
        paint();
      })
    );

    app.querySelectorAll("[data-sort]").forEach((button) =>
      button.addEventListener("click", () => {
        sortKey = button.dataset.sort;
        paint();
      })
    );

    app.querySelectorAll("[data-toggle]").forEach((button) =>
      button.addEventListener("click", () => {
        const id = `${activeVariation}:${button.dataset.toggle}`;
        if (expanded.has(id)) expanded.delete(id);
        else expanded.add(id);
        paint();
      })
    );

    const search = app.querySelector("[data-search]");
    if (search) {
      search.addEventListener("input", (event) => {
        query = event.target.value;
        paint();
        // The repaint replaces the input, so put the cursor back where it was.
        const next = app.querySelector("[data-search]");
        next?.focus();
        next?.setSelectionRange(next.value.length, next.value.length);
      });
    }

    detach();
    detach = attachCountdown(app, () => store.schedule);

    if (!firstPaint) revealAll(app);
    firstPaint = false;
  };

  paint();

  let scheduled = null;
  const unsubscribe = store.subscribe(() => {
    clearTimeout(scheduled);
    scheduled = setTimeout(paint, 300);
  });

  return () => {
    clearTimeout(scheduled);
    detach();
    unsubscribe();
  };
}
