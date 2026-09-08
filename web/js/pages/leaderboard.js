// The live board. Variation tabs, expandable rows, rank-change flashes.

import { store } from "../main.js";
import { attachCountdown, renderCountdown } from "../countdown.js";
import { VARIATION_META, esc, money, relativeTime, signed } from "../ui.js";

let activeVariation = 1;
let expanded = new Set();
const lastRanks = new Map(); // "V:key" -> rank, for the movement arrows

function movement(row) {
  const id = `${row.variation}:${row.key}`;
  const previous = lastRanks.get(id);
  lastRanks.set(id, row.rank);
  if (previous === undefined || previous === row.rank) return "";

  const up = row.rank < previous;
  const delta = Math.abs(previous - row.rank);
  return `<span class="ml-1.5 font-mono text-[10px] ${up ? "text-gain" : "text-loss"}">
            ${up ? "▲" : "▼"}${delta}
          </span>`;
}

function rankBadge(row) {
  if (row.disqualified) {
    return `<span class="grid h-8 w-8 place-items-center rounded-lg border border-loss/40 bg-loss/10 text-loss">✕</span>`;
  }
  const styles = {
    1: "border-gold/60 bg-gold/15 text-gold",
    2: "border-ink-dim/40 bg-ink-dim/10 text-ink-dim",
    3: "border-[#c98a4b]/50 bg-[#c98a4b]/10 text-[#c98a4b]",
  };
  const style = styles[row.rank] || "border-line bg-surface-2 text-ink-faint";
  return `<span class="grid h-8 w-8 place-items-center rounded-lg border font-heading text-sm font-bold ${style}">
            ${row.rank}
          </span>`;
}

function detailGrid(row) {
  const cells = [
    ["Games played", row.games],
    ["Mean final capital", money(row.mean_final_capital)],
    ["Best game", signed(row.best_net_profit)],
    ["Worst game", signed(row.worst_net_profit)],
    ["Std deviation", money(row.std_net_profit)],
    ["Rounds won", row.wins],
    ["Survival rate", `${Math.round((row.survival_rate ?? 0) * 100)}%`],
    ["Errors / timeouts", `${row.errors} / ${row.timeouts}`],
  ];

  return `
    <div class="border-t border-line/70 bg-void/50 px-5 py-4">
      <dl class="grid grid-cols-2 gap-x-6 gap-y-3 md:grid-cols-4">
        ${cells
          .map(
            ([label, value]) => `
          <div>
            <dt class="font-mono text-[10px] uppercase tracking-[0.16em] text-ink-faint">${label}</dt>
            <dd class="mt-0.5 font-mono text-sm text-ink">${esc(value)}</dd>
          </div>`
          )
          .join("")}
      </dl>
      ${
        row.disqualified
          ? `<p class="mt-4 rounded-lg border border-loss/35 bg-loss/10 px-3 py-2 font-mono text-xs text-loss">
               Disqualified — ${esc(row.reason || "sandbox violation")}
             </p>`
          : ""
      }
    </div>`;
}

function boardRow(row) {
  const isOpen = expanded.has(`${row.variation}:${row.key}`);
  const positive = (row.mean_net_profit || 0) >= 0;
  const spread = row.std_net_profit || 0;

  return `
    <div class="border-b border-line/60 last:border-b-0" data-row="${esc(row.key)}">
      <button class="flex w-full items-center gap-4 px-4 py-3.5 text-left transition-colors hover:bg-surface-2/50"
              data-toggle="${esc(row.key)}" aria-expanded="${isOpen}">
        ${rankBadge(row)}

        <span class="min-w-0 flex-1">
          <span class="flex items-center font-mono text-sm text-ink">
            ${esc(row.key)}${movement(row)}
          </span>
          ${row.name ? `<span class="block truncate text-xs text-ink-faint">${esc(row.name)}</span>` : ""}
        </span>

        <span class="hidden w-28 text-right sm:block">
          <span class="block font-mono text-xs text-ink-faint">σ ${money(spread)}</span>
          <span class="block font-mono text-xs text-ink-faint">${row.wins} wins</span>
        </span>

        <span class="w-28 text-right font-mono text-sm font-semibold tabular-nums
                     ${row.disqualified ? "text-ink-faint line-through" : positive ? "text-gain" : "text-loss"}">
          ${signed(row.mean_net_profit)}
        </span>

        <span class="text-ink-faint transition-transform ${isOpen ? "rotate-90" : ""}">›</span>
      </button>
      ${isOpen ? detailGrid(row) : ""}
    </div>`;
}

function emptyBoard(variation) {
  return `
    <div class="grid place-items-center px-6 py-16 text-center">
      <p class="font-mono text-sm text-ink-faint">Nothing on the board for variation ${variation} yet.</p>
      <p class="mt-2 max-w-sm text-sm text-ink-dim">
        Bots appear here after the next showdown finishes.
      </p>
      <a href="/submit" data-link class="btn-gold mt-6">Submit a bot</a>
    </div>`;
}

export async function renderLeaderboard(app) {
  const paint = () => {
    const rows = (store.rows || []).filter((row) => row.variation === activeVariation);
    rows.sort((a, b) => (a.rank || 9999) - (b.rank || 9999));

    const schedule = store.schedule;
    const state = store.state || {};
    const live = schedule.running;

    app.innerHTML = `
      <section class="mx-auto max-w-6xl px-5 py-12">
        <div class="grid gap-8 lg:grid-cols-[1fr_auto] lg:items-center">
          <div>
            <span class="chip ${live ? "border-gold/50 text-gold" : ""}">
              <span class="h-1.5 w-1.5 rounded-full ${live ? "animate-pulse-dot bg-gold" : "bg-gain"}"></span>
              ${live ? "Showdown in progress" : "Board settled"}
            </span>
            <h1 class="mt-4 font-heading text-4xl font-bold md:text-5xl">Leaderboard</h1>
            <p class="mt-3 max-w-xl text-sm leading-relaxed text-ink-dim">
              Each bot plays ${esc(state.repeats ?? 3)} independent
              ${(state.repeats ?? 3) === 1 ? "run" : "runs"} of
              ${esc(state.num_rounds ?? 2000)} rounds in randomised groups of
              ${esc(state.group_size ?? 20)}. The figure below is the mean net profit
              across those runs — luck averages out, strategy does not.
            </p>
            <p class="mt-3 font-mono text-xs text-ink-faint">
              last showdown ${esc(state.last_showdown ? relativeTime(state.last_showdown.finished_at) : "never")}
              ${state.last_showdown ? `· ${esc(state.last_showdown.games)} games played` : ""}
            </p>
          </div>
          <div class="panel p-5 lg:w-72">${renderCountdown()}</div>
        </div>

        ${
          live && schedule.progress_total
            ? `<div class="panel mt-8 p-4">
                 <div class="flex items-center justify-between font-mono text-xs text-ink-dim">
                   <span>playing games…</span>
                   <span>${schedule.progress_done} / ${schedule.progress_total}</span>
                 </div>
                 <div class="mt-2 h-1.5 overflow-hidden rounded-full bg-line">
                   <div class="h-full rounded-full bg-gradient-to-r from-gold-soft to-gold transition-all duration-500"
                        data-progress-bar="${Math.round((schedule.progress_done / schedule.progress_total) * 100)}"></div>
                 </div>
               </div>`
            : ""
        }

        <div class="mt-8 flex flex-wrap gap-2" role="tablist">
          ${[1, 2, 3]
            .map((id) => {
              const meta = VARIATION_META[id];
              const active = id === activeVariation;
              const count = (store.rows || []).filter((r) => r.variation === id).length;
              return `
                <button role="tab" aria-selected="${active}" data-variation="${id}"
                        class="btn ${active ? "btn-gold" : "btn-ghost"} px-4 py-2 text-xs">
                  V${id} · ${meta.name}
                  <span class="rounded-full bg-void/25 px-1.5 py-0.5 font-mono text-[10px]">${count}</span>
                </button>`;
            })
            .join("")}
        </div>

        <div class="panel mt-5 overflow-hidden">
          <div class="flex items-center gap-4 border-b border-line bg-surface-2/50 px-4 py-2.5
                      font-mono text-[10px] uppercase tracking-[0.18em] text-ink-faint">
            <span class="w-8">#</span>
            <span class="flex-1">Bot</span>
            <span class="hidden w-28 text-right sm:block">Spread</span>
            <span class="w-28 text-right">Net profit</span>
            <span class="w-3"></span>
          </div>
          ${rows.length ? rows.map(boardRow).join("") : emptyBoard(activeVariation)}
        </div>
      </section>`;

    // CSP forbids a `style` attribute; CSSOM assignment is allowed.
    app.querySelectorAll("[data-progress-bar]").forEach((bar) => {
      bar.style.width = `${bar.dataset.progressBar}%`;
    });

    app.querySelectorAll("[data-variation]").forEach((button) =>
      button.addEventListener("click", () => {
        activeVariation = Number(button.dataset.variation);
        paint();
        reattach();
      })
    );

    app.querySelectorAll("[data-toggle]").forEach((button) =>
      button.addEventListener("click", () => {
        const id = `${activeVariation}:${button.dataset.toggle}`;
        expanded.has(id) ? expanded.delete(id) : expanded.add(id);
        paint();
        reattach();
      })
    );
  };

  let detach = () => {};
  const reattach = () => {
    detach();
    detach = attachCountdown(app, () => store.schedule);
  };

  paint();
  reattach();

  let scheduled = null;
  const unsubscribe = store.subscribe(() => {
    clearTimeout(scheduled);
    scheduled = setTimeout(() => {
      paint();
      reattach();
    }, 300);
  });

  return () => {
    clearTimeout(scheduled);
    detach();
    unsubscribe();
  };
}
