// App shell: shared state, navigation, routing, and the live connection.

import { api, openStream } from "./api.js";
import { serverNow, syncClock } from "./countdown.js";
import { observeCounters, observeReveals, startCursor, startParallax } from "./motion.js";
import { clockParts, esc, registerLateVariation, relativeTime, toast } from "./ui.js";
import { registerLatePayoff } from "./payoff.js";
import { registerLateRules } from "./pages/rules.js";

import { renderHome } from "./pages/home.js";
import { renderLeaderboard } from "./pages/leaderboard.js";
import { renderRules } from "./pages/rules.js";
import { renderSubmit } from "./pages/submit.js";
import { renderLogin } from "./pages/login.js";
import { renderAdmin } from "./pages/admin.js";

// --- shared state --------------------------------------------------------------

export const store = {
  me: { signed_in: false },
  state: null,
  rows: [],
  listeners: new Set(),

  set(patch) {
    Object.assign(this, patch);
    this.listeners.forEach((fn) => {
      try {
        fn(this);
      } catch (error) {
        console.error(error);
      }
    });
  },

  subscribe(fn) {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  },

  get schedule() {
    return this.state?.schedule || {};
  },
};

// --- routing -------------------------------------------------------------------

const ROUTES = [
  { path: "/", render: renderHome, nav: "Index", index: "01" },
  { path: "/leaderboard", render: renderLeaderboard, nav: "Board", index: "02" },
  { path: "/rules", render: renderRules, nav: "Problem", index: "03" },
  { path: "/submit", render: renderSubmit, nav: "Submit", index: "04" },
  { path: "/login", render: renderLogin },
  { path: "/admin", render: renderAdmin },
];

let disposePage = null;
let disposeMotion = () => {};
let menuOpen = false;

function matchRoute(pathname) {
  const clean = pathname.replace(/\/+$/, "") || "/";
  return ROUTES.find((route) => route.path === clean) || null;
}

export async function navigate(path, { replace = false } = {}) {
  if (replace) history.replaceState({}, "", path);
  else history.pushState({}, "", path);
  await renderRoute();
}

async function renderRoute() {
  const app = document.getElementById("app");
  const route = matchRoute(location.pathname);

  menuOpen = false;

  if (disposePage) {
    try {
      disposePage();
    } catch (error) {
      console.error(error);
    }
    disposePage = null;
  }
  disposeMotion();

  if (!route) {
    app.innerHTML = notFound();
    renderNav();
    return;
  }

  app.innerHTML = `<div class="bleed py-32"><p class="label animate-blip">Loading</p></div>`;
  renderNav();

  try {
    disposePage = (await route.render(app)) || null;
  } catch (error) {
    console.error(error);
    app.innerHTML = errorPanel(error.message);
    app.querySelector("[data-reload]")?.addEventListener("click", () => location.reload());
  }

  const stopReveals = observeReveals(app);
  const stopCounters = observeCounters(app);
  disposeMotion = () => {
    stopReveals();
    stopCounters();
  };

  window.scrollTo({ top: 0, behavior: "instant" in window ? "instant" : "auto" });
}

function notFound() {
  return `
    <section class="bleed py-32">
      <p class="label">Error 404</p>
      <h1 class="d1 mt-8 font-display">Nothing<br>here</h1>
      <p class="lede mt-8 max-w-md">That route does not exist. The auction is this way.</p>
      <a href="/" data-link class="btn-solid mt-10">Back to the floor <span>→</span></a>
    </section>`;
}

function errorPanel(message) {
  return `
    <section class="bleed py-32">
      <p class="label text-loss">Error</p>
      <h1 class="d2 mt-8 font-display">Something broke</h1>
      <p class="mt-6 font-mono text-sm text-ink-2">${esc(message)}</p>
      <button class="btn-line mt-10" data-reload>Reload the page</button>
    </section>`;
}

// --- chrome --------------------------------------------------------------------

// A chart glyph rather than a lettermark: three bids, one of them winning.
const MARK = `
  <svg viewBox="0 0 24 24" class="h-6 w-6" aria-hidden="true" fill="none">
    <rect x="1" y="13" width="4" height="9" class="fill-ink-3"/>
    <rect x="10" y="8" width="4" height="14" class="fill-ink-3"/>
    <rect x="19" y="2" width="4" height="20" class="fill-flame"/>
  </svg>`;

const THEME_ICON = {
  dark: `<svg viewBox="0 0 24 24" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true">
           <circle cx="12" cy="12" r="4.2"/>
           <path d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M19.1 4.9l-1.8 1.8M6.7 17.3l-1.8 1.8"/>
         </svg>`,
  light: `<svg viewBox="0 0 24 24" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true">
            <path d="M20 14.2A8.2 8.2 0 0 1 9.8 4a8.4 8.4 0 1 0 10.2 10.2z"/>
          </svg>`,
};

function navLinks(current) {
  return ROUTES.filter((route) => route.nav)
    .map((route) => {
      const active = route.path === current;
      return `
        <a href="${route.path}" data-link
           class="group flex items-baseline gap-2 font-mono text-[11px] uppercase tracking-[0.18em]
                  transition-colors ${active ? "text-flame" : "text-ink-2 hover:text-ink"}"
           ${active ? 'aria-current="page"' : ""}>
          <span class="text-[9px] ${active ? "text-flame" : "text-ink-3"}">${route.index}</span>
          ${route.nav}
        </a>`;
    })
    .join("");
}

function overlayLinks(current) {
  return ROUTES.filter((route) => route.nav)
    .map(
      (route) => `
      <a href="${route.path}" data-link
         class="hair-b flex items-baseline justify-between py-5 transition-colors
                ${route.path === current ? "text-flame" : "hover:text-flame"}">
        <span class="d2 font-display">${route.nav}</span>
        <span class="font-mono text-[11px] text-ink-3">${route.index}</span>
      </a>`
    )
    .join("");
}

function accountBlock(me) {
  if (!me.signed_in) {
    return `<a href="/login" data-link class="btn-solid whitespace-nowrap px-3 py-2.5 sm:px-4">Sign in</a>`;
  }

  return `
    <div class="flex items-center gap-2">
      ${me.is_admin ? `<a href="/admin" data-link class="tag hover:border-flame hover:text-flame">Control</a>` : ""}
      <span class="hidden items-center gap-2 border border-line px-2.5 py-1.5 sm:flex">
        <span class="dot text-flame"></span>
        <span class="max-w-[8rem] truncate font-mono text-[11px]">${esc(me.roll || me.name)}</span>
      </span>
      <button data-logout class="btn-quiet px-2.5 py-2">Out</button>
    </div>`;
}

function renderNav() {
  const header = document.getElementById("nav");
  const current = location.pathname.replace(/\/+$/, "") || "/";
  const theme = window.QGTheme?.current?.() || "dark";
  const next = theme === "dark" ? "light" : "dark";

  header.className = `sticky top-0 z-40 hair-b backdrop-blur-md ${
    menuOpen ? "bg-void" : "bg-void/85"
  }`;

  header.innerHTML = `
    <div class="bleed flex h-16 items-center gap-6">
      <a href="/" data-link class="flex items-center gap-3">
        ${MARK}
        <span class="font-display text-lg leading-none">Quant&nbsp;Guild</span>
      </a>

      <nav class="ml-4 hidden items-center gap-7 md:flex" aria-label="Primary">
        ${navLinks(current)}
      </nav>

      <div class="ml-auto flex items-center gap-3">
        <span class="hidden font-mono text-[11px] text-ink-3 lg:inline" data-nav-status></span>
        <button data-theme-toggle class="btn-quiet px-2 py-2"
                title="Switch to the ${next} theme" aria-label="Switch to the ${next} theme">
          ${THEME_ICON[theme] || THEME_ICON.dark}
        </button>
        ${accountBlock(store.me)}
        <button data-menu class="btn-line px-3 py-2 md:hidden"
                aria-expanded="${menuOpen}" aria-label="Menu">${menuOpen ? "Close" : "Menu"}</button>
      </div>
    </div>

    ${
      menuOpen
        ? `<nav class="bleed hair pb-10 pt-4 md:hidden" aria-label="Primary">${overlayLinks(current)}</nav>`
        : ""
    }`;
}

/**
 * The one-line status in the masthead, ticking once a second.
 *
 * It is written straight into the node rather than going through a re-render,
 * so a countdown in the header never fights the router for the DOM.
 */
function startNavStatus() {
  setInterval(() => {
    const node = document.querySelector("[data-nav-status]");
    if (!node) return;

    const schedule = store.schedule;
    if (schedule.running) {
      node.textContent = "● showdown live";
      node.className = "hidden font-mono text-[11px] text-flame lg:inline";
      return;
    }
    node.className = "hidden font-mono text-[11px] text-ink-3 lg:inline";
    if (!schedule.enabled) {
      node.textContent = "showdowns paused";
      return;
    }
    const nextAt = Number(schedule.next_run_at) || 0;
    if (!nextAt) {
      node.textContent = "";
      return;
    }
    const { hours, minutes, seconds } = clockParts(nextAt - serverNow());
    node.textContent = `next showdown ${hours}:${minutes}:${seconds}`;
  }, 1000);
}

// --- announcement --------------------------------------------------------------

// Dismissals are keyed by the message itself, so publishing a new announcement
// shows it again to somebody who dismissed the last one.
const announcementKey = (text) =>
  `qg-announce-${Array.from(text).reduce((h, c) => (h * 31 + c.charCodeAt(0)) | 0, 7)}`;

function renderAnnouncement() {
  const host = document.getElementById("announce");
  if (!host) return;

  const text = (store.state?.announcement || "").trim();
  if (!text) {
    host.innerHTML = "";
    return;
  }

  let dismissed = false;
  try {
    dismissed = localStorage.getItem(announcementKey(text)) === "1";
  } catch (error) {
    /* site data blocked, show it, which is the safe direction */
  }
  if (dismissed) {
    host.innerHTML = "";
    return;
  }

  host.innerHTML = `
    <div class="bg-flame text-void">
      <div class="bleed flex items-start gap-4 py-2.5">
        <span class="mt-px shrink-0 font-mono text-[10px] uppercase tracking-[0.22em]">Notice</span>
        <p class="flex-1 text-sm leading-relaxed">${esc(text)}</p>
        <button data-dismiss-announce class="shrink-0 font-mono text-xs" aria-label="Dismiss">✕</button>
      </div>
    </div>`;

  host.querySelector("[data-dismiss-announce]")?.addEventListener("click", () => {
    try {
      localStorage.setItem(announcementKey(text), "1");
    } catch (error) {
      /* nothing to persist to; it will reappear next load */
    }
    host.innerHTML = "";
  });
}

function renderFooterStatus() {
  const node = document.querySelector("[data-footer-status]");
  if (!node) return;
  const state = store.state;
  if (!state) {
    node.textContent = "";
    return;
  }
  const counts = state.counts || { participants: 0, per_variation: {} };
  const bots = Object.values(counts.per_variation || {}).reduce((a, b) => a + b, 0);
  node.textContent =
    `${counts.participants} participants · ${bots} bots · ` +
    `last showdown ${state.last_showdown ? relativeTime(state.last_showdown.finished_at) : "never"}`;
}

// --- variations released later -------------------------------------------------

// Variations 3 and 4 are not in the shipped bundle. Their names, rules, worked
// example and payoff arithmetic live in `server/late_variations.js`, which
// `/api/variations/late.js` refuses to serve until the admin switches one of
// them on. So before mock auction 1 a participant reading the page source finds
// nothing about them, and the moment the admin flips the switch the running
// `state` event brings every open tab here without a reload.

let lateLoaded = false;
let lateLoading = null;

function ensureLateVariations(state) {
  if (lateLoaded || lateLoading) return lateLoading;
  const variations = (state?.variations || []).map(Number);
  if (!variations.some((id) => id === 3 || id === 4)) return null;

  lateLoading = import("/api/variations/late.js")
    .then((module) => {
      Object.entries(module.META || {}).forEach(([id, meta]) =>
        registerLateVariation(Number(id), meta)
      );
      registerLatePayoff(module.evaluate);
      registerLateRules(module);
      lateLoaded = true;
      // The copy arrived after the page was drawn, so draw it again.
      store.set({});
    })
    .catch((error) => {
      // A 404 here is the normal state before release, not a fault.
      console.debug("late variations not available", error);
    })
    .finally(() => {
      lateLoading = null;
    });

  return lateLoading;
}

// --- live connection -----------------------------------------------------------

let pollTimer = null;

async function refreshState() {
  try {
    const state = await api.state();
    syncClock(state.now);
    store.set({ state });
    ensureLateVariations(state);
  } catch (error) {
    console.error("state refresh failed", error);
  }
}

async function refreshLeaderboard() {
  try {
    const { rows } = await api.leaderboard();
    store.set({ rows });
  } catch (error) {
    console.error("leaderboard refresh failed", error);
  }
}

function startPolling() {
  if (pollTimer) return;
  pollTimer = setInterval(() => {
    refreshState();
    refreshLeaderboard();
  }, 30_000);
}

function connectLive() {
  let failures = 0;

  openStream({
    onLeaderboard: (rows) => store.set({ rows: Array.isArray(rows) ? rows : [] }),
    onSchedule: (schedule) => store.set({ state: { ...(store.state || {}), schedule } }),

    // An admin changed a setting. This is what makes releasing a variation
    // reach every open tab immediately instead of on the next reload.
    onState: (state) => {
      syncClock(state.now);
      store.set({ state });
      ensureLateVariations(state);
    },

    onProgress: ({ done, total }) =>
      store.set({
        state: {
          ...(store.state || {}),
          schedule: { ...store.schedule, running: true, progress_done: done, progress_total: total },
        },
      }),

    // Fires the moment a showdown starts, before any game has finished. Without
    // this the page would keep showing "starting…" until the first game landed,
    // fifteen seconds or more with real 2000-round games.
    onShowdown: ({ status }) => {
      const running = status === "started";
      store.set({
        state: { ...(store.state || {}), schedule: { ...store.schedule, running } },
      });
      // The finish rewrites next_run_at, so re-read the authoritative clock.
      if (!running) refreshState();
    },

    onError: () => {
      failures += 1;
      // EventSource retries by itself; after a few genuine failures fall back to
      // polling so the page keeps updating even if SSE is blocked entirely.
      if (failures >= 3) startPolling();
    },
  });
}

// --- boot ----------------------------------------------------------------------

function interceptClicks() {
  document.addEventListener("click", (event) => {
    if (event.target.closest("[data-theme-toggle]")) {
      event.preventDefault();
      window.QGTheme?.toggle();
      renderNav();
      return;
    }

    if (event.target.closest("[data-menu]")) {
      event.preventDefault();
      menuOpen = !menuOpen;
      renderNav();
      return;
    }

    if (event.target.closest("[data-logout]")) {
      event.preventDefault();
      api
        .logout()
        .then(() => {
          store.set({ me: { signed_in: false } });
          toast("Signed out.", "info");
          navigate("/");
        })
        .catch((error) => toast(error.message, "error"));
      return;
    }

    const link = event.target.closest("a[data-link]");
    if (!link) return;
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;

    event.preventDefault();
    const href = link.getAttribute("href");

    // Tapping the current page in the mobile menu should close it, not push a
    // second history entry for the page you are already on.
    if (href === location.pathname) {
      if (menuOpen) {
        menuOpen = false;
        renderNav();
      }
      return;
    }
    navigate(href);
  });

  window.addEventListener("popstate", renderRoute);
}

async function boot() {
  interceptClicks();
  startCursor();
  startParallax();

  store.subscribe(() => {
    renderNav();
    renderAnnouncement();
    renderFooterStatus();
  });

  const [me] = await Promise.allSettled([api.me(), refreshState(), refreshLeaderboard()]);
  if (me.status === "fulfilled") store.set({ me: me.value });

  renderAnnouncement();
  renderFooterStatus();
  await renderRoute();
  startNavStatus();
  connectLive();

  // A tab left open overnight should not show a stale board.
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) refreshState();
  });
}

boot();
