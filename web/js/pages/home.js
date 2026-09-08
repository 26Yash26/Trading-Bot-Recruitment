// Landing page: what the game is, when the next showdown fires, who is winning.

import { store } from "../main.js";
import { attachCountdown, renderCountdown } from "../countdown.js";
import { VARIATION_META, animateNumber, esc, relativeTime, signed } from "../ui.js";

const STEPS = [
  {
    n: "01",
    title: "You are dealt a value",
    body: "Every round each bot privately draws xᵢ from a uniform distribution. You see yours and nobody else's.",
  },
  {
    n: "02",
    title: "Everyone bids at once",
    body: "One number in [0, max bid]. Bid more than your capital and the engine files it as a zero.",
  },
  {
    n: "03",
    title: "Highest bid takes it",
    body: "Ties all win. The payoff depends on which variation you are playing — that is the whole game.",
  },
  {
    n: "04",
    title: "Capital carries over",
    body: "Profit and loss compound across 2000 rounds. Hit zero and you sit out the rest of the game.",
  },
];

const TIMELINE = [
  { date: "09 Sep", label: "Problem statement released", done: true },
  { date: "Every 2 h", label: "Showdown — the field replays, the board resets", live: true },
  { date: "20 Sep", label: "Mock auction, full stats sent to every participant" },
  { date: "23 Sep", label: "Final submission deadline, 23:59" },
  { date: "24 Sep", label: "Final evaluation and shortlisting" },
];

function tickerTape(rows) {
  const items = rows.length
    ? rows.slice(0, 18)
    : [{ key: "AWAITING SUBMISSIONS", mean_net_profit: 0, variation: 0 }];

  const cell = (row) => {
    const positive = (row.mean_net_profit || 0) >= 0;
    return `
      <span class="flex shrink-0 items-center gap-2 px-5 font-mono text-xs">
        <span class="text-ink-faint">${row.variation ? `V${row.variation}` : "—"}</span>
        <span class="text-ink">${esc(row.key)}</span>
        <span class="${positive ? "text-gain" : "text-loss"}">${signed(row.mean_net_profit)}</span>
      </span>`;
  };

  const strip = items.map(cell).join("");
  return `
    <div class="relative overflow-hidden border-y border-line/70 bg-surface/50 py-2.5">
      <div class="flex w-max animate-marquee">
        <div class="flex">${strip}</div>
        <div class="flex" aria-hidden="true">${strip}</div>
      </div>
      <div class="pointer-events-none absolute inset-y-0 left-0 w-24 bg-gradient-to-r from-void to-transparent"></div>
      <div class="pointer-events-none absolute inset-y-0 right-0 w-24 bg-gradient-to-l from-void to-transparent"></div>
    </div>`;
}

function variationCard(id) {
  const meta = VARIATION_META[id];
  const detail = {
    1: "Your own value sets the prize. Overbid and you pay for the privilege of winning.",
    2: "The prize is the best value on the table, so winning is worth the same to everyone — the race is purely about the bid.",
    3: "Same prize as V2, but the runner-up hands back half the winner's surplus. Second place actively hurts.",
  }[id];

  return `
    <article data-reveal="${id * 80}"
             class="panel group relative overflow-hidden p-6 transition-transform duration-300 hover:-translate-y-1">
      <div class="absolute inset-x-0 -top-px h-px bg-gradient-to-r from-transparent via-gold/60 to-transparent
                  opacity-0 transition-opacity group-hover:opacity-100"></div>
      <div class="flex items-center justify-between">
        <span class="chip ${meta.ring} ${meta.accent}">Variation ${id}</span>
        <span class="font-heading text-4xl font-bold text-line-bright transition-colors group-hover:text-gold/30">
          0${id}
        </span>
      </div>
      <h3 class="mt-4 font-heading text-lg font-bold">${meta.name}</h3>
      <p class="mt-2 min-h-[3.5rem] text-sm leading-relaxed text-ink-dim">${detail}</p>
      <div class="mt-4 rounded-xl border border-line bg-void/60 px-4 py-3">
        <p class="font-mono text-[10px] uppercase tracking-[0.2em] text-ink-faint">Winner payoff</p>
        <p class="mt-1 font-mono text-sm ${meta.accent}">${meta.formula}</p>
      </div>
    </article>`;
}

function podium(rows) {
  const top = rows
    .filter((row) => row.variation === 1 && !row.disqualified)
    .sort((a, b) => (a.rank || 999) - (b.rank || 999))
    .slice(0, 5);

  if (!top.length) {
    return `
      <div class="panel grid place-items-center px-6 py-14 text-center">
        <p class="font-mono text-sm text-ink-faint">No showdown has run yet.</p>
        <p class="mt-2 max-w-sm text-sm text-ink-dim">
          The board fills in the moment the first auction finishes. Submit a bot and you are in it.
        </p>
        <a href="/submit" data-link class="btn-gold mt-6">Submit a bot</a>
      </div>`;
  }

  const medal = ["text-gold", "text-ink-dim", "text-[#c98a4b]"];
  return `
    <div class="panel divide-y divide-line/70 overflow-hidden">
      ${top
        .map((row, index) => {
          const positive = (row.mean_net_profit || 0) >= 0;
          return `
            <div class="flex items-center gap-4 px-5 py-3.5 transition-colors hover:bg-surface-2/60">
              <span class="w-8 font-heading text-lg font-bold ${medal[index] || "text-ink-faint"}">
                ${row.rank}
              </span>
              <span class="flex-1 truncate font-mono text-sm text-ink">${esc(row.key)}</span>
              <span class="font-mono text-sm tabular-nums ${positive ? "text-gain" : "text-loss"}">
                ${signed(row.mean_net_profit)}
              </span>
            </div>`;
        })
        .join("")}
    </div>`;
}

function statTile(value, label, digits = 0) {
  return `
    <div class="panel px-5 py-4">
      <p class="stat-value" data-stat data-target="${value}" data-digits="${digits}">0</p>
      <p class="stat-label">${label}</p>
    </div>`;
}

export async function renderHome(app) {
  const paint = () => {
    const state = store.state || {};
    const counts = state.counts || { participants: 0, per_variation: {} };
    const bots = Object.values(counts.per_variation || {}).reduce((a, b) => a + b, 0);
    const last = state.last_showdown;

    app.innerHTML = `
      <section class="relative mx-auto max-w-6xl px-5 pt-16 pb-10 md:pt-24">
        <div class="grid items-center gap-12 md:grid-cols-[1.15fr_auto]">
          <div>
            <span class="chip border-gold/40 text-gold">
              <span class="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-gold"></span>
              Recruitment open · odd sem 2026
            </span>

            <h1 class="mt-5 font-heading text-5xl font-bold leading-[1.05] md:text-7xl">
              Bid. Win.<br><span class="text-gradient-gold">Survive 2000 rounds.</span>
            </h1>

            <p class="mt-5 max-w-xl text-base leading-relaxed text-ink-dim md:text-lg">
              Write one Python class. It plays a sealed-bid auction against nineteen other bots,
              two thousand rounds at a time, on a distribution nobody tells you.
              Every two hours the whole field plays again and this board is rewritten.
            </p>

            <div class="mt-8 flex flex-wrap items-center gap-3">
              <a href="/submit" data-link class="btn-gold">Submit your bot</a>
              <a href="/rules" data-link class="btn-ghost">Read the rules</a>
              <a href="/public/starter-kit.zip" class="btn-ghost" download>Starter kit</a>
            </div>

            <div class="mt-10 grid grid-cols-2 gap-3 sm:grid-cols-4">
              ${statTile(counts.participants, "Participants")}
              ${statTile(bots, "Bots in play")}
              ${statTile(state.num_rounds || 2000, "Rounds / game")}
              ${statTile(state.group_size || 20, "Bots / group")}
            </div>
          </div>

          <div class="justify-self-center">
            <div class="panel panel-glow p-6">
              ${renderCountdown()}
              <p class="mt-3 text-center font-mono text-[11px] text-ink-faint">
                last run ${esc(last ? relativeTime(last.finished_at) : "never")}
              </p>
            </div>
          </div>
        </div>
      </section>

      ${tickerTape(store.rows || [])}

      <section class="mx-auto max-w-6xl px-5 py-16">
        <h2 class="font-heading text-2xl font-bold md:text-3xl">How a round works</h2>
        <div class="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          ${STEPS.map(
            (step, index) => `
            <div data-reveal="${index * 70}" class="panel relative p-5">
              <span class="font-mono text-xs text-gold">${step.n}</span>
              <h3 class="mt-2 font-heading text-base font-bold">${step.title}</h3>
              <p class="mt-2 text-sm leading-relaxed text-ink-dim">${step.body}</p>
            </div>`
          ).join("")}
        </div>
      </section>

      <div class="rule-gold mx-auto max-w-5xl"></div>

      <section class="mx-auto max-w-6xl px-5 py-16">
        <div class="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 class="font-heading text-2xl font-bold md:text-3xl">Three variations</h2>
            <p class="mt-2 text-sm text-ink-dim">One file each. Submit as many as you like.</p>
          </div>
          <a href="/rules" data-link class="link-underline text-sm">Full payoff rules →</a>
        </div>
        <div class="mt-8 grid gap-4 md:grid-cols-3">
          ${[1, 2, 3].map(variationCard).join("")}
        </div>
      </section>

      <section class="mx-auto max-w-6xl px-5 pb-20">
        <div class="grid gap-8 lg:grid-cols-[1.2fr_1fr]">
          <div>
            <div class="flex items-center justify-between">
              <h2 class="font-heading text-2xl font-bold">Standing — Variation 1</h2>
              <a href="/leaderboard" data-link class="link-underline text-sm">Full board →</a>
            </div>
            <div class="mt-5">${podium(store.rows || [])}</div>
          </div>

          <div>
            <h2 class="font-heading text-2xl font-bold">Timeline</h2>
            <ol class="mt-5 space-y-0">
              ${TIMELINE.map(
                (item) => `
                <li class="relative flex gap-4 pb-6 pl-1 last:pb-0">
                  <span class="absolute left-[5px] top-3 h-full w-px bg-line last:hidden"></span>
                  <span class="relative z-10 mt-2 h-2.5 w-2.5 shrink-0 rounded-full
                    ${item.live ? "animate-pulse-dot bg-gold" : item.done ? "bg-gain" : "bg-line-bright"}"></span>
                  <div>
                    <p class="font-mono text-[11px] uppercase tracking-widest text-ink-faint">${item.date}</p>
                    <p class="mt-0.5 text-sm text-ink">${item.label}</p>
                  </div>
                </li>`
              ).join("")}
            </ol>
          </div>
        </div>
      </section>`;

    app.querySelectorAll("[data-stat]").forEach((el) =>
      animateNumber(el, Number(el.dataset.target), { digits: Number(el.dataset.digits) })
    );
  };

  paint();

  // `paint` replaces the DOM the countdown drives, so its interval has to be
  // torn down and re-attached around every repaint or they pile up invisibly.
  let detachCountdown = attachCountdown(app, () => store.schedule);
  let scheduled = null;

  const unsubscribe = store.subscribe(() => {
    clearTimeout(scheduled);
    scheduled = setTimeout(() => {
      detachCountdown();
      paint();
      detachCountdown = attachCountdown(app, () => store.schedule);
    }, 400);
  });

  return () => {
    clearTimeout(scheduled);
    detachCountdown();
    unsubscribe();
  };
}
