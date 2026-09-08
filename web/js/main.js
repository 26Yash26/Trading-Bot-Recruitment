// App shell: shared state, navigation, routing, and the live connection.

import { api, openStream } from "./api.js";
import { startBackdrop } from "./backdrop.js";
import { syncClock } from "./countdown.js";
import { esc, observeReveals, toast } from "./ui.js";

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
  { path: "/", render: renderHome, nav: "Home" },
  { path: "/leaderboard", render: renderLeaderboard, nav: "Leaderboard" },
  { path: "/rules", render: renderRules, nav: "Rules" },
  { path: "/submit", render: renderSubmit, nav: "Submit" },
  { path: "/login", render: renderLogin },
  { path: "/admin", render: renderAdmin },
];

let disposePage = null;

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

  if (disposePage) {
    try {
      disposePage();
    } catch (error) {
      console.error(error);
    }
    disposePage = null;
  }

  if (!route) {
    app.innerHTML = notFound();
    renderNav();
    return;
  }

  app.innerHTML = `<div class="mx-auto max-w-6xl px-5 py-16 text-center text-ink-faint">Loading…</div>`;
  renderNav();

  try {
    disposePage = (await route.render(app)) || null;
  } catch (error) {
    console.error(error);
    app.innerHTML = errorPanel(error.message);
  }

  observeReveals(app);
  window.scrollTo({ top: 0, behavior: "instant" in window ? "instant" : "auto" });
}

function notFound() {
  return `
    <section class="mx-auto grid max-w-3xl place-items-center px-5 py-28 text-center">
      <p class="font-mono text-7xl font-bold text-gradient-gold">404</p>
      <h1 class="mt-4 text-2xl font-bold">No such page</h1>
      <p class="mt-2 text-ink-dim">That route does not exist. The auction is this way.</p>
      <a href="/" data-link class="btn-gold mt-7">Back to the floor</a>
    </section>`;
}

function errorPanel(message) {
  return `
    <section class="mx-auto max-w-3xl px-5 py-24 text-center">
      <h1 class="text-2xl font-bold text-loss">Something broke</h1>
      <p class="mt-3 font-mono text-sm text-ink-dim">${esc(message)}</p>
      <button class="btn-ghost mt-7" onclick="location.reload()">Reload</button>
    </section>`;
}

// --- navigation bar ------------------------------------------------------------

function renderNav() {
  const header = document.getElementById("nav");
  const current = location.pathname.replace(/\/+$/, "") || "/";
  const me = store.me;

  const links = ROUTES.filter((route) => route.nav)
    .map((route) => {
      const active = route.path === current;
      return `
        <a href="${route.path}" data-link
           class="relative rounded-lg px-3 py-1.5 text-sm font-medium transition-colors
                  ${active ? "text-gold" : "text-ink-dim hover:text-ink"}">
          ${route.nav}
          ${active ? '<span class="absolute inset-x-2 -bottom-px h-px bg-gold"></span>' : ""}
        </a>`;
    })
    .join("");

  const adminLink = me.is_admin
    ? `<a href="/admin" data-link class="chip border-violet/40 text-violet hover:border-violet">Admin</a>`
    : "";

  const account = me.signed_in
    ? `<div class="flex items-center gap-2">
         ${adminLink}
         <span class="hidden items-center gap-2 rounded-full border border-line-bright bg-surface-2/70 px-3 py-1.5 sm:flex">
           <span class="grid h-5 w-5 place-items-center rounded-full bg-gold text-[10px] font-bold text-void">
             ${esc((me.name || "?").trim().charAt(0).toUpperCase())}
           </span>
           <span class="max-w-[9rem] truncate font-mono text-xs text-ink">${esc(me.roll || me.name)}</span>
         </span>
         <button data-logout class="rounded-lg px-2.5 py-1.5 text-xs text-ink-faint transition-colors hover:text-loss">
           Sign out
         </button>
       </div>`
    : `<a href="/login" data-link class="btn-gold px-4 py-2 text-xs">Sign in</a>`;

  header.innerHTML = `
    <div class="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-5">
      <a href="/" data-link class="group flex items-center gap-2.5">
        <span class="grid h-8 w-8 place-items-center rounded-lg border border-gold/40 bg-gold/10
                     font-heading text-sm font-bold text-gold transition-transform group-hover:scale-105">Q</span>
        <span class="font-heading text-base font-bold tracking-tight">
          Quant <span class="text-gold">Guild</span>
        </span>
      </a>
      <nav class="hidden items-center gap-1 md:flex">${links}</nav>
      <div class="flex items-center gap-2">${account}</div>
    </div>
    <nav class="flex items-center justify-center gap-1 border-t border-line/60 py-1.5 md:hidden">${links}</nav>`;
}

// --- live connection -----------------------------------------------------------

let pollTimer = null;

async function refreshState() {
  try {
    const state = await api.state();
    syncClock(state.now);
    store.set({ state });
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
    onProgress: ({ done, total }) =>
      store.set({
        state: {
          ...(store.state || {}),
          schedule: { ...store.schedule, running: true, progress_done: done, progress_total: total },
        },
      }),

    // Fires the moment a showdown starts, before any game has finished. Without
    // this the page would keep showing "starting…" until the first game landed —
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

function interceptLinks() {
  document.addEventListener("click", (event) => {
    const logout = event.target.closest("[data-logout]");
    if (logout) {
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
    if (href !== location.pathname) navigate(href);
  });

  window.addEventListener("popstate", renderRoute);
}

async function boot() {
  startBackdrop(document.getElementById("backdrop"));
  interceptLinks();

  store.subscribe(renderNav);

  const [me] = await Promise.allSettled([api.me(), refreshState(), refreshLeaderboard()]);
  if (me.status === "fulfilled") store.set({ me: me.value });

  await renderRoute();
  connectLive();

  // A tab left open overnight should not show a stale board.
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) refreshState();
  });
}

boot();
