// Admin console — the only place the showdown's shape can be changed.
//
// Access is checked on the server for every one of these endpoints; hiding the
// page from a non-admin is a courtesy, not the control.

import { api } from "../api.js";
import { navigate, store } from "../main.js";
import { esc, relativeTime, toast } from "../ui.js";

const INTERVAL_PRESETS = [15, 30, 60, 120, 240, 480];

let data = null;
let tab = "showdown";

function field(key, label, value, { type = "number", step, min, hint = "" } = {}) {
  return `
    <label class="block">
      <span class="font-mono text-[10px] uppercase tracking-[0.16em] text-ink-faint">${label}</span>
      <input class="field mt-1.5" type="${type}" name="${key}" value="${esc(value)}"
             ${step ? `step="${step}"` : ""} ${min !== undefined ? `min="${min}"` : ""}>
      ${hint ? `<span class="mt-1 block text-[11px] text-ink-faint">${hint}</span>` : ""}
    </label>`;
}

function toggle(key, label, value, hint = "") {
  return `
    <button type="button" data-toggle-setting="${key}"
            class="flex w-full items-center justify-between gap-4 rounded-xl border border-line
                   bg-void/60 px-4 py-3 text-left transition-colors hover:border-line-bright">
      <span>
        <span class="block text-sm font-medium text-ink">${label}</span>
        ${hint ? `<span class="mt-0.5 block text-[11px] text-ink-faint">${hint}</span>` : ""}
      </span>
      <span class="relative h-6 w-11 shrink-0 rounded-full transition-colors ${value ? "bg-gold" : "bg-line-bright"}">
        <span class="absolute top-0.5 h-5 w-5 rounded-full bg-void transition-all ${value ? "left-[1.375rem]" : "left-0.5"}"></span>
      </span>
    </button>`;
}

function estimate(settings, participants) {
  const groups = Math.max(1, Math.ceil(participants / Math.max(1, settings.group_size)));
  const games =
    (settings.variations?.length || 3) *
    settings.repeats *
    groups *
    Math.max(1, settings.starting_capitals?.length || 1);
  const seconds = (games * 15 * (settings.num_rounds / 2000)) / Math.max(1, settings.workers);
  return { games, seconds };
}

function showdownTab(settings, schedule, counts) {
  const { games, seconds } = estimate(settings, counts.participants || 0);
  const minutes = seconds / 60;
  const tooLong = seconds > settings.interval_minutes * 60 * 0.7;

  return `
    <div class="grid gap-5 lg:grid-cols-2">
      <div class="panel p-6">
        <h3 class="font-heading text-base font-bold">Cadence</h3>
        <p class="mt-1 text-xs text-ink-faint">How often the whole field replays.</p>

        <div class="mt-5 space-y-3">
          ${toggle("showdown_enabled", "Run showdowns automatically", settings.showdown_enabled,
                   "Turn off to freeze the board without stopping submissions.")}
          ${toggle("submissions_open", "Accept new submissions", settings.submissions_open)}
        </div>

        <div class="mt-5">
          <span class="font-mono text-[10px] uppercase tracking-[0.16em] text-ink-faint">Interval</span>
          <div class="mt-2 flex flex-wrap gap-2">
            ${INTERVAL_PRESETS.map(
              (m) => `
              <button type="button" data-interval="${m}"
                      class="btn ${settings.interval_minutes === m ? "btn-gold" : "btn-ghost"} px-3 py-1.5 text-xs">
                ${m < 60 ? `${m}m` : `${m / 60}h`}
              </button>`
            ).join("")}
          </div>
          <div class="mt-3">
            ${field("interval_minutes", "Custom interval (minutes)", settings.interval_minutes, { min: 1 })}
          </div>
        </div>

        <div class="mt-6 rounded-xl border border-line bg-void/60 p-4">
          <div class="flex items-center justify-between text-sm">
            <span class="text-ink-dim">Next showdown</span>
            <span class="font-mono text-ink">
              ${schedule.next_run_at ? esc(new Date(schedule.next_run_at * 1000).toLocaleString()) : "—"}
            </span>
          </div>
          <div class="mt-2 flex items-center justify-between text-sm">
            <span class="text-ink-dim">Last run</span>
            <span class="font-mono text-ink">${esc(relativeTime(schedule.last_run_at))}</span>
          </div>
          ${
            schedule.running
              ? `<div class="mt-4">
                   <div class="flex justify-between font-mono text-xs text-gold">
                     <span>running</span>
                     <span>${schedule.progress_done} / ${schedule.progress_total}</span>
                   </div>
                   <div class="mt-1.5 h-1.5 overflow-hidden rounded-full bg-line">
                     <div class="h-full bg-gold transition-all"
                          data-progress-bar="${schedule.progress_total
                            ? Math.round((schedule.progress_done / schedule.progress_total) * 100)
                            : 0}"></div>
                   </div>
                 </div>`
              : ""
          }
          <button class="btn-gold mt-4 w-full" data-run-now ${schedule.running ? "disabled" : ""}>
            ${schedule.running ? "Showdown in progress…" : "Run a showdown now"}
          </button>
        </div>
      </div>

      <div class="panel p-6">
        <h3 class="font-heading text-base font-bold">Game shape</h3>
        <p class="mt-1 text-xs text-ink-faint">What each showdown actually plays.</p>

        <div class="mt-5">
          <span class="font-mono text-[10px] uppercase tracking-[0.16em] text-ink-faint">Variations in play</span>
          <div class="mt-2 flex gap-2">
            ${[1, 2, 3]
              .map((id) => {
                const on = (settings.variations || []).includes(id);
                return `<button type="button" data-variation-toggle="${id}"
                                class="btn ${on ? "btn-gold" : "btn-ghost"} px-4 py-1.5 text-xs">V${id}</button>`;
              })
              .join("")}
          </div>
        </div>

        <div class="mt-5 grid gap-4 sm:grid-cols-2">
          ${field("num_rounds", "Rounds per game", settings.num_rounds, { min: 1 })}
          ${field("group_size", "Bots per group", settings.group_size, { min: 2 })}
          ${field("repeats", "Repeats", settings.repeats, { min: 1, hint: "Averages out luck (PS §8)" })}
          ${field("workers", "Parallel workers", settings.workers, { min: 1 })}
          ${field("max_bid", "Max bid", settings.max_bid, { step: "0.01", min: 0 })}
          ${field("starting_capitals", "Starting capitals", (settings.starting_capitals || []).join(", "), {
            type: "text",
            hint: "Comma-separated; each value is swept",
          })}
        </div>

        <div class="mt-5 rounded-xl border p-4 ${tooLong ? "border-loss/40 bg-loss/10" : "border-line bg-void/60"}">
          <p class="font-mono text-[10px] uppercase tracking-[0.16em] text-ink-faint">Estimated cost</p>
          <p class="mt-1 font-mono text-sm ${tooLong ? "text-loss" : "text-ink"}">
            ${games} games · about ${minutes < 1 ? "<1" : Math.ceil(minutes)} min
          </p>
          ${
            tooLong
              ? `<p class="mt-1.5 text-xs text-loss">
                   That is more than 70% of the interval. Raise the interval, cut repeats,
                   or add workers.
                 </p>`
              : ""
          }
        </div>
      </div>
    </div>`;
}

function sandboxTab(settings, isolation) {
  const tiers = {
    docker: ["Docker", "Container with no network, read-only rootfs, all capabilities dropped.", "text-gain"],
    bwrap: ["Bubblewrap", "User + network + PID namespace, read-only /usr, tmpfs working directory.", "text-gain"],
    unshare: ["Network namespace", "Network is unreachable, but the filesystem is only rlimit-protected.", "text-gold"],
    sudo: ["Dedicated user", "Runs as an unprivileged account. No namespace isolation.", "text-gold"],
    plain: ["Plain subprocess", "Resource limits only — acceptable for local development, not for the VM.", "text-loss"],
  };
  const [name, blurb, colour] = tiers[isolation] || tiers.plain;

  return `
    <div class="grid gap-5 lg:grid-cols-2">
      <div class="panel p-6">
        <h3 class="font-heading text-base font-bold">Isolation in use</h3>
        <p class="mt-4 font-heading text-2xl font-bold ${colour}">${name}</p>
        <p class="mt-2 text-sm leading-relaxed text-ink-dim">${blurb}</p>
        ${
          isolation === "plain"
            ? `<p class="mt-4 rounded-lg border border-loss/40 bg-loss/10 px-3 py-2 text-xs text-loss">
                 Install bubblewrap (<span class="font-mono">apt install bubblewrap</span>) or Docker
                 on this host before running real submissions.
               </p>`
            : ""
        }
        <div class="mt-5 grid gap-4 sm:grid-cols-2">
          ${field("round_timeout", "Round timeout (s)", settings.round_timeout, { step: "0.1", min: 0.1 })}
          ${field("mem_mb", "Memory ceiling (MB)", settings.mem_mb, { min: 64 })}
        </div>
        <p class="mt-3 text-[11px] leading-relaxed text-ink-faint">
          The problem statement asks participants to stay under 100 MB. The enforced ceiling is
          deliberately higher — importing numpy and pandas alone costs most of that, and a false
          disqualification is far worse than a generous limit.
        </p>
      </div>

      <div class="panel p-6">
        <h3 class="font-heading text-base font-bold">Hidden distribution</h3>
        <p class="mt-1 text-xs text-ink-faint">
          Never sent to a browser except this page. Four blocks of 500 rounds.
        </p>
        <div class="mt-5 space-y-3">
          ${(settings.block_bounds || [])
            .map(
              (bounds, index) => `
            <div class="grid grid-cols-[auto_1fr_1fr] items-center gap-3">
              <span class="font-mono text-xs text-ink-faint">B${index + 1}</span>
              <input class="field" type="number" step="0.01" data-bound="${index}:0" value="${esc(bounds[0])}">
              <input class="field" type="number" step="0.01" data-bound="${index}:1" value="${esc(bounds[1])}">
            </div>`
            )
            .join("")}
        </div>
        <div class="mt-4">${field("seed", "Master seed", settings.seed, { min: 0 })}</div>
      </div>
    </div>`;
}

function fieldTab(submissions, counts, settings) {
  const banned = new Set((settings.banned_rolls || []).map((r) => r.toUpperCase()));

  return `
    <div class="panel p-6">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <h3 class="font-heading text-base font-bold">
          Active submissions
          <span class="ml-2 font-mono text-xs text-ink-faint">
            ${counts.participants} participants · ${submissions.length} files
          </span>
        </h3>
        <div class="flex gap-2">
          ${[1, 2, 3]
            .map(
              (id) =>
                `<span class="chip">V${id} · ${counts.per_variation?.[id] || 0}</span>`
            )
            .join("")}
        </div>
      </div>

      <div class="mt-5 max-h-[28rem] overflow-y-auto rounded-xl border border-line">
        ${
          submissions.length
            ? submissions
                .map(
                  (row) => `
          <div class="flex items-center gap-3 border-b border-line/60 px-4 py-2.5 last:border-b-0">
            <span class="w-24 font-mono text-sm ${banned.has(row.roll) ? "text-loss line-through" : "text-ink"}">
              ${esc(row.roll)}
            </span>
            <span class="chip py-0.5">V${esc(row.variation)}</span>
            <span class="min-w-0 flex-1 truncate text-xs text-ink-dim">${esc(row.name || row.email)}</span>
            <span class="font-mono text-xs text-ink-faint">${esc(relativeTime(row.created_at))}</span>
            <button data-ban="${esc(row.roll)}" data-banned="${banned.has(row.roll)}"
                    class="rounded-lg border border-line-bright px-2.5 py-1 text-[11px] transition-colors
                           ${banned.has(row.roll) ? "text-gain hover:border-gain/50" : "text-loss hover:border-loss/50"}">
              ${banned.has(row.roll) ? "Unban" : "Ban"}
            </button>
          </div>`
                )
                .join("")
            : `<p class="px-4 py-10 text-center font-mono text-sm text-ink-faint">No submissions yet.</p>`
        }
      </div>
    </div>`;
}

function historyTab(showdowns, audit) {
  return `
    <div class="grid gap-5 lg:grid-cols-2">
      <div class="panel p-6">
        <h3 class="font-heading text-base font-bold">Showdowns</h3>
        <div class="mt-4 max-h-96 space-y-2 overflow-y-auto">
          ${
            showdowns.length
              ? showdowns
                  .map(
                    (row) => `
            <div class="rounded-lg border border-line bg-void/50 px-3 py-2">
              <div class="flex items-center justify-between text-xs">
                <span class="font-mono ${row.status === "done" ? "text-gain" : row.status === "running" ? "text-gold" : "text-loss"}">
                  #${row.id} ${esc(row.status)}
                </span>
                <span class="font-mono text-ink-faint">${esc(relativeTime(row.started_at))}</span>
              </div>
              <p class="mt-0.5 font-mono text-[11px] text-ink-dim">
                ${row.games} games${row.finished_at ? ` · ${Math.round(row.finished_at - row.started_at)}s` : ""}
              </p>
              ${row.error ? `<p class="mt-1 text-[11px] text-loss">${esc(row.error)}</p>` : ""}
            </div>`
                  )
                  .join("")
              : `<p class="py-8 text-center font-mono text-sm text-ink-faint">Nothing yet.</p>`
          }
        </div>
      </div>

      <div class="panel p-6">
        <h3 class="font-heading text-base font-bold">Audit log</h3>
        <div class="mt-4 max-h-96 space-y-1.5 overflow-y-auto font-mono text-[11px]">
          ${audit
            .map(
              (row) => `
            <div class="flex gap-2 border-b border-line/40 pb-1.5">
              <span class="w-16 shrink-0 text-ink-faint">${esc(relativeTime(row.at))}</span>
              <span class="w-20 shrink-0 text-gold">${esc(row.action)}</span>
              <span class="min-w-0 flex-1 truncate text-ink-dim">${esc(row.actor)} ${esc(row.detail)}</span>
            </div>`
            )
            .join("")}
        </div>
      </div>
    </div>`;
}

export async function renderAdmin(app) {
  if (!store.me.signed_in) {
    navigate("/login", { replace: true });
    return;
  }
  if (!store.me.is_admin) {
    app.innerHTML = `
      <section class="mx-auto grid max-w-lg place-items-center px-5 py-28 text-center">
        <p class="font-heading text-5xl font-bold text-loss">403</p>
        <h1 class="mt-4 text-xl font-bold">Admins only</h1>
        <p class="mt-2 text-sm text-ink-dim">This account is not on the admin list.</p>
        <a href="/" data-link class="btn-ghost mt-7">Back to the floor</a>
      </section>`;
    return;
  }

  const load = async () => {
    const [settings, submissions, showdowns, audit] = await Promise.all([
      api.admin.settings(),
      api.admin.submissions(),
      api.admin.showdowns(),
      api.admin.audit(),
    ]);
    data = {
      settings: settings.settings,
      schedule: settings.schedule,
      isolation: settings.isolation,
      counts: settings.counts,
      submissions: submissions.submissions,
      showdowns: showdowns.showdowns,
      audit: audit.audit,
    };
  };

  const save = async (changes) => {
    try {
      const response = await api.admin.update(changes);
      data.settings = response.settings;
      data.schedule = response.schedule;
      toast("Saved.", "ok", 2200);
      paint();
    } catch (error) {
      toast(error.message, "error");
    }
  };

  const TABS = [
    ["showdown", "Showdown"],
    ["sandbox", "Sandbox & secrets"],
    ["field", "Submissions"],
    ["history", "History"],
  ];

  const paint = () => {
    const { settings, schedule, counts, isolation, submissions, showdowns, audit } = data;

    app.innerHTML = `
      <section class="mx-auto max-w-6xl px-5 py-12">
        <div class="flex flex-wrap items-end justify-between gap-4">
          <div>
            <span class="chip border-violet/40 text-violet">Admin</span>
            <h1 class="mt-3 font-heading text-3xl font-bold md:text-4xl">Control room</h1>
            <p class="mt-2 text-sm text-ink-dim">
              Everything here takes effect on the next showdown. Changing the interval reschedules immediately.
            </p>
          </div>
          <button class="btn-ghost" data-refresh>Refresh</button>
        </div>

        <div class="mt-7 flex flex-wrap gap-2">
          ${TABS.map(
            ([id, label]) =>
              `<button data-tab="${id}" class="btn ${tab === id ? "btn-gold" : "btn-ghost"} px-4 py-2 text-xs">${label}</button>`
          ).join("")}
        </div>

        <div class="mt-6">
          ${
            tab === "showdown"
              ? showdownTab(settings, schedule, counts)
              : tab === "sandbox"
                ? sandboxTab(settings, isolation)
                : tab === "field"
                  ? fieldTab(submissions, counts, settings)
                  : historyTab(showdowns, audit)
          }
        </div>

        ${
          tab === "showdown" || tab === "sandbox"
            ? `<div class="mt-6 flex flex-wrap items-center gap-3">
                 <button class="btn-gold" data-save>Save settings</button>
                 <span class="text-xs text-ink-faint">Toggles and interval presets save on click.</span>
               </div>`
            : ""
        }

        <div class="panel mt-8 p-5">
          <label class="block">
            <span class="font-mono text-[10px] uppercase tracking-[0.16em] text-ink-faint">
              Site announcement (shown to everyone; leave blank to hide)
            </span>
            <input class="field mt-1.5" type="text" name="announcement" value="${esc(settings.announcement || "")}">
          </label>
          <button class="btn-ghost mt-3" data-save-announcement>Publish announcement</button>
        </div>
      </section>`;

    wire();
  };

  const numeric = new Set([
    "interval_minutes", "num_rounds", "group_size", "repeats", "workers", "mem_mb", "seed",
  ]);
  const floaty = new Set(["max_bid", "round_timeout"]);

  const collect = () => {
    const changes = {};
    app.querySelectorAll("input[name]").forEach((input) => {
      const key = input.name;
      if (key === "starting_capitals") {
        const values = input.value
          .split(",")
          .map((part) => Number(part.trim()))
          .filter((n) => Number.isFinite(n) && n > 0);
        if (values.length) changes[key] = values;
      } else if (numeric.has(key)) {
        const value = parseInt(input.value, 10);
        if (Number.isFinite(value)) changes[key] = value;
      } else if (floaty.has(key)) {
        const value = parseFloat(input.value);
        if (Number.isFinite(value)) changes[key] = value;
      } else if (key === "announcement") {
        changes[key] = input.value;
      }
    });

    const bounds = [];
    app.querySelectorAll("[data-bound]").forEach((input) => {
      const [block, side] = input.dataset.bound.split(":").map(Number);
      bounds[block] = bounds[block] || [0, 0];
      bounds[block][side] = parseFloat(input.value) || 0;
    });
    if (bounds.length) changes.block_bounds = bounds;

    return changes;
  };

  const wire = () => {
    // CSP forbids a `style` attribute; CSSOM assignment is allowed.
    app.querySelectorAll("[data-progress-bar]").forEach((bar) => {
      bar.style.width = `${bar.dataset.progressBar}%`;
    });

    app.querySelectorAll("[data-tab]").forEach((button) =>
      button.addEventListener("click", () => {
        tab = button.dataset.tab;
        paint();
      })
    );

    app.querySelector("[data-refresh]")?.addEventListener("click", async () => {
      await load();
      paint();
      toast("Refreshed.", "info", 1800);
    });

    app.querySelectorAll("[data-toggle-setting]").forEach((button) =>
      button.addEventListener("click", () => {
        const key = button.dataset.toggleSetting;
        save({ [key]: !data.settings[key] });
      })
    );

    app.querySelectorAll("[data-interval]").forEach((button) =>
      button.addEventListener("click", () =>
        save({ interval_minutes: Number(button.dataset.interval) })
      )
    );

    app.querySelectorAll("[data-variation-toggle]").forEach((button) =>
      button.addEventListener("click", () => {
        const id = Number(button.dataset.variationToggle);
        const current = new Set(data.settings.variations || []);
        current.has(id) ? current.delete(id) : current.add(id);
        if (!current.size) {
          toast("At least one variation has to stay enabled.", "error");
          return;
        }
        save({ variations: [...current].sort() });
      })
    );

    app.querySelector("[data-save]")?.addEventListener("click", () => save(collect()));

    app.querySelector("[data-save-announcement]")?.addEventListener("click", () => {
      const input = app.querySelector('input[name="announcement"]');
      save({ announcement: input.value });
    });

    app.querySelector("[data-run-now]")?.addEventListener("click", async (event) => {
      event.target.disabled = true;
      try {
        await api.admin.runNow();
        toast("Showdown starting…", "ok");
        setTimeout(async () => {
          await load();
          paint();
        }, 1500);
      } catch (error) {
        toast(error.message, "error");
        event.target.disabled = false;
      }
    });

    app.querySelectorAll("[data-ban]").forEach((button) =>
      button.addEventListener("click", async () => {
        const roll = button.dataset.ban;
        const banned = button.dataset.banned === "true";
        try {
          await api.admin.ban(roll, !banned);
          await load();
          paint();
          toast(`${roll} ${banned ? "unbanned" : "banned"}.`, "ok");
        } catch (error) {
          toast(error.message, "error");
        }
      })
    );
  };

  await load();
  paint();

  const unsubscribe = store.subscribe(() => {
    if (!data) return;
    data.schedule = store.schedule;
    if (tab === "showdown") paint();
  });

  return unsubscribe;
}
