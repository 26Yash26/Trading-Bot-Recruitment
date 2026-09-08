// Admin console — the only place the competition's shape can be changed.
//
// Access is checked on the server for every one of these endpoints; hiding the
// page from a non-admin is a courtesy, not the control.
//
// Every setting the problem statement defines is reachable from here: which
// variations are released, the block structure, the capital draw, the tournament
// grouping, the hidden distribution, the sandbox, and the site's own copy.

import { api } from "../api.js";
import { navigate, store } from "../main.js";
import { revealAll } from "../motion.js";
import {
  ALL_VARIATIONS,
  VARIATION_META,
  applyBarWidths,
  describeInterval,
  esc,
  formatDeadline,
  relativeTime,
  toast,
} from "../ui.js";

const INTERVAL_PRESETS = [15, 30, 60, 120, 240, 480];

const GROUPINGS = [
  ["random", "Random", "Iterations 1 and 2 — the field is reshuffled on a fresh seed."],
  ["balanced", "Strength-balanced", "Iteration 3 — sorted by points and dealt in a snake, so groups are equal in average strength."],
  ["finals", "Finals", "Iterations 4 and 5 — only the leading bots, head to head."],
];

const TABS = [
  ["showdown", "Showdown"],
  ["game", "Game & tournament"],
  ["secrets", "Secrets & sandbox"],
  ["field", "Submissions"],
  ["site", "Site"],
  ["history", "History"],
];

let data = null;
let tab = "showdown";

// --- small builders ------------------------------------------------------------

function field(key, label, value, { type = "number", step, min, max, hint = "" } = {}) {
  return `
    <label class="block">
      <span class="label">${label}</span>
      <input class="field mt-3" type="${type}" name="${key}" value="${esc(value)}"
             ${step ? `step="${step}"` : ""}
             ${min !== undefined ? `min="${min}"` : ""}
             ${max !== undefined ? `max="${max}"` : ""}>
      ${hint ? `<span class="mt-2 block font-mono text-[10px] leading-relaxed text-ink-3">${hint}</span>` : ""}
    </label>`;
}

function toggle(key, label, value, hint = "") {
  return `
    <button type="button" data-toggle-setting="${key}" aria-pressed="${Boolean(value)}"
            class="panel-2 flex w-full items-center justify-between gap-5 px-5 py-4 text-left
                   transition-colors hover:border-line-2">
      <span>
        <span class="block text-sm font-semibold">${label}</span>
        ${hint ? `<span class="mt-1 block font-mono text-[10px] leading-relaxed text-ink-3">${hint}</span>` : ""}
      </span>
      <span class="switch-track" data-on="${Boolean(value)}"><span class="switch-knob"></span></span>
    </button>`;
}

function panelHead(title, note = "") {
  return `
    <div class="hair-b p-6">
      <h3 class="d4 font-display">${title}</h3>
      ${note ? `<p class="mt-2 font-mono text-[10px] leading-relaxed text-ink-3">${note}</p>` : ""}
    </div>`;
}

function estimate(settings, participants) {
  const groups = Math.max(1, Math.ceil(participants / Math.max(1, settings.group_size)));
  const games = (settings.variations?.length || 0) * (settings.iterations || 1) * groups;
  const seconds = (games * 15 * (settings.num_rounds / 2000)) / Math.max(1, settings.workers);
  return { games, seconds };
}

// --- the variation switchboard -------------------------------------------------

/**
 * Releasing a variation here releases it on the site.
 *
 * Variations 3 and 4 are meant to go live only after mock auction 1, so they
 * ship switched off. Turning one on adds it to the home page, the leaderboard,
 * the problem statement and the submit form, and starts its files being played;
 * turning one off removes all of that. The change is pushed to every open tab
 * over the event stream, so nobody has to reload.
 */
function variationBoard(settings, counts) {
  const on = new Set((settings.variations || []).map(Number));

  return `
    <div class="panel">
      ${panelHead(
        "Variations released",
        "Switching one on adds it to the home page, the board, the problem statement and the " +
          "submit form, and starts its files being played. Existing submissions are kept either way."
      )}
      <div class="divide-y divide-line">
        ${ALL_VARIATIONS.map((id) => {
          const meta = VARIATION_META[id];
          const live = on.has(id);
          const entries = counts?.per_variation?.[id] || 0;
          return `
            <button type="button" data-variation-toggle="${id}" aria-pressed="${live}"
                    class="flex w-full items-center gap-5 px-6 py-5 text-left transition-colors hover:bg-void-3">
              <span class="font-display text-2xl leading-none ${live ? meta.ink : "text-line-2"}">
                ${meta.index}
              </span>
              <span class="min-w-0 flex-1">
                <span class="block text-sm font-semibold">${esc(meta.name)}</span>
                <span class="mt-1 block font-mono text-[10px] text-ink-3">
                  ${esc(meta.formula)} · ${entries} ${entries === 1 ? "file" : "files"} submitted
                </span>
              </span>
              <span class="hidden font-mono text-[10px] uppercase tracking-[0.18em] sm:block
                           ${live ? "text-gain" : "text-ink-3"}">
                ${live ? "released" : "hidden"}
              </span>
              <span class="switch-track" data-on="${live}"><span class="switch-knob"></span></span>
            </button>`;
        }).join("")}
      </div>
      ${
        on.size === 0
          ? `<p class="border-l-2 border-l-loss px-6 py-4 font-mono text-[11px] text-loss">
               Nothing is in play. The site is telling participants there is no auction.
             </p>`
          : ""
      }
    </div>`;
}

// --- tabs ----------------------------------------------------------------------

function showdownTab(settings, schedule, counts) {
  return `
    <div class="space-y-6">
      ${variationBoard(settings, counts)}

      <div class="grid items-start gap-6 lg:grid-cols-2">
        <div class="panel">
          ${panelHead(
            "Cadence",
            `The practice board replays the whole field ${esc(describeInterval(settings.interval_minutes))}.`
          )}
          <div class="space-y-4 p-6">
            ${toggle(
              "showdown_enabled",
              "Run showdowns automatically",
              settings.showdown_enabled,
              "Turn off to freeze the board without closing submissions."
            )}
            ${toggle(
              "submissions_open",
              "Accept new submissions",
              settings.submissions_open,
              "The upload form refuses everything while this is off."
            )}

            <div class="pt-2">
              <span class="label">Interval</span>
              <div class="mt-3 flex flex-wrap gap-2">
                ${INTERVAL_PRESETS.map(
                  (m) => `
                  <button type="button" data-interval="${m}"
                          class="${
                            settings.interval_minutes === m ? "btn-solid" : "btn-line"
                          } px-3 py-2">${m < 60 ? `${m}m` : `${m / 60}h`}</button>`
                ).join("")}
              </div>
              <div class="mt-5">
                ${field("interval_minutes", "Custom interval (minutes)", settings.interval_minutes, {
                  min: 1,
                })}
              </div>
            </div>
          </div>
        </div>

        <div class="panel">
          ${panelHead("Run state")}
          <div class="p-6">
            <div class="flex items-center justify-between text-sm">
              <span class="text-ink-2">Next showdown</span>
              <span class="font-mono text-[11px]">
                ${schedule.next_run_at ? esc(new Date(schedule.next_run_at * 1000).toLocaleString()) : "—"}
              </span>
            </div>
            <div class="hair mt-4 flex items-center justify-between pt-4 text-sm">
              <span class="text-ink-2">Last run</span>
              <span class="font-mono text-[11px]">${esc(relativeTime(schedule.last_run_at))}</span>
            </div>
            ${
              schedule.running
                ? `<div class="mt-6">
                     <div class="flex justify-between font-mono text-[11px] text-flame">
                       <span>running</span>
                       <span>${esc(schedule.progress_done)} / ${esc(schedule.progress_total)}</span>
                     </div>
                     <div class="bar-track mt-3">
                       <div class="bar bg-flame" data-bar-width="${
                         schedule.progress_total
                           ? Math.round((schedule.progress_done / schedule.progress_total) * 100)
                           : 0
                       }"></div>
                     </div>
                   </div>`
                : ""
            }
            ${
              schedule.last_error
                ? `<p class="mt-5 font-mono text-[10px] leading-relaxed text-loss">
                     last error: ${esc(schedule.last_error)}
                   </p>`
                : ""
            }
            <button class="btn-solid mt-6 w-full" data-run-now ${schedule.running ? "disabled" : ""}>
              ${schedule.running ? "Showdown in progress…" : "Run a showdown now"}
            </button>
          </div>
        </div>
      </div>
    </div>`;
}

function gameTab(settings, counts) {
  const { games, seconds } = estimate(settings, counts.participants || 0);
  const minutes = seconds / 60;
  const tooLong = seconds > settings.interval_minutes * 60 * 0.7;
  const blocks = Math.max(1, Math.ceil(settings.num_rounds / Math.max(1, settings.block_size)));

  return `
    <div class="grid gap-6 lg:grid-cols-2">
      <div class="panel">
        ${panelHead("The game", `${blocks} blocks of ${settings.block_size} rounds.`)}
        <div class="grid gap-5 p-6 sm:grid-cols-2">
          ${field("num_rounds", "Rounds per game", settings.num_rounds, { min: 1 })}
          ${field("block_size", "Rounds per block", settings.block_size, {
            min: 1,
            hint: "The distribution and every capital are redrawn at each boundary.",
          })}
          ${field("group_size", "Bots per group", settings.group_size, { min: 2 })}
          ${field("workers", "Parallel workers", settings.workers, { min: 1 })}
        </div>
      </div>

      <div class="panel">
        ${panelHead("Tournament", "Problem statement §9.")}
        <div class="p-6">
          <div class="grid gap-5 sm:grid-cols-2">
            ${field("iterations", "Iterations per variation", settings.iterations, { min: 1 })}
            ${field("finals_size", "Finals field size", settings.finals_size, { min: 2 })}
          </div>

          <div class="mt-6">
            <span class="label">Grouping</span>
            <div class="mt-3 space-y-2">
              ${GROUPINGS.map(
                ([value, title, note]) => `
                <button type="button" data-grouping="${value}"
                        class="panel-2 block w-full px-5 py-4 text-left transition-colors
                               ${settings.grouping === value ? "border-flame" : "hover:border-line-2"}">
                  <span class="flex items-center gap-3">
                    <span class="h-2 w-2 ${settings.grouping === value ? "bg-flame" : "bg-line-2"}"></span>
                    <span class="text-sm font-semibold">${title}</span>
                  </span>
                  <span class="mt-2 block font-mono text-[10px] leading-relaxed text-ink-3">${note}</span>
                </button>`
              ).join("")}
            </div>
          </div>
        </div>
      </div>

      <div class="panel lg:col-span-2">
        ${panelHead(
          "Capital draw at every block boundary",
          "Problem statement §3.1 — κ ~ U[lo, hi], capital = max(κ·M + u, floor·M)."
        )}
        <div class="grid gap-5 p-6 sm:grid-cols-2 xl:grid-cols-5">
          ${field("kappa_lo", "κ minimum", settings.kappa_lo, { step: "0.05", min: 0 })}
          ${field("kappa_hi", "κ maximum", settings.kappa_hi, { step: "0.05", min: 0 })}
          ${field("jitter_lo", "Jitter u minimum", settings.jitter_lo, { step: "0.5" })}
          ${field("jitter_hi", "Jitter u maximum", settings.jitter_hi, { step: "0.5" })}
          ${field("floor_fraction", "Floor, as a fraction of M", settings.floor_fraction, {
            step: "0.01",
            min: 0,
          })}
        </div>
        <p class="hair px-6 py-5 font-mono text-[11px] text-ink-2" data-capital-preview></p>
      </div>

      <div class="panel lg:col-span-2 ${tooLong ? "border-loss" : ""}">
        ${panelHead("Estimated cost of one showdown")}
        <div class="p-6">
          <p class="font-display text-3xl ${tooLong ? "text-loss" : ""}">
            ${games} games · about ${minutes < 1 ? "<1" : Math.ceil(minutes)} min
          </p>
          <p class="mt-3 font-mono text-[11px] text-ink-3">
            ${settings.variations?.length || 0} variations ×
            ${settings.iterations} iterations ×
            ${Math.max(1, Math.ceil((counts.participants || 0) / Math.max(1, settings.group_size)))} groups
          </p>
          ${
            tooLong
              ? `<p class="mt-4 border-l-2 border-l-loss pl-4 text-sm leading-relaxed text-loss">
                   That is more than 70% of the interval. Raise the interval, cut iterations,
                   or add workers.
                 </p>`
              : ""
          }
        </div>
      </div>
    </div>`;
}

function secretsTab(settings, isolation) {
  const tiers = {
    docker: ["Docker", "Container with no network, read-only rootfs, all capabilities dropped.", "text-gain"],
    bwrap: ["Bubblewrap", "User + network + PID namespace, read-only /usr, tmpfs working directory.", "text-gain"],
    unshare: ["Network namespace", "Network is unreachable, but the filesystem is only rlimit-protected.", "text-flame"],
    sudo: ["Dedicated user", "Runs as an unprivileged account. No namespace isolation.", "text-flame"],
    plain: ["Plain subprocess", "Resource limits only — fine for local development, not for the VM.", "text-loss"],
  };
  const [name, blurb, colour] = tiers[isolation] || tiers.plain;

  return `
    <div class="grid gap-6 lg:grid-cols-2">
      <div class="panel">
        ${panelHead("Hidden distribution", "Never sent to a browser except this page.")}
        <div class="p-6">
          <div class="space-y-4">
            ${(settings.block_bounds || [])
              .map(
                (bounds, index) => `
              <div class="grid grid-cols-[auto_1fr_1fr] items-center gap-4">
                <span class="font-mono text-[11px] text-ink-3">B${index + 1}</span>
                <input class="field" type="number" step="0.01" data-bound="${index}:0"
                       value="${esc(bounds[0])}" aria-label="Block ${index + 1} minimum">
                <input class="field" type="number" step="0.01" data-bound="${index}:1"
                       value="${esc(bounds[1])}" aria-label="Block ${index + 1} maximum">
              </div>`
              )
              .join("")}
          </div>
          <p class="mt-4 font-mono text-[10px] leading-relaxed text-ink-3">
            One row per block: minimum and maximum of that block's uniform distribution. The maximum
            is also what the capital draw and the whole scoring scheme are scaled by.
          </p>
          <div class="mt-6">${field("seed", "Master seed", settings.seed, { min: 0 })}</div>
        </div>
      </div>

      <div class="panel">
        ${panelHead("Sandbox")}
        <div class="p-6">
          <p class="d3 font-display ${colour}">${name}</p>
          <p class="mt-3 text-sm leading-relaxed text-ink-2">${blurb}</p>
          ${
            isolation === "plain"
              ? `<p class="mt-5 border-l-2 border-l-loss pl-4 font-mono text-[11px] leading-relaxed text-loss">
                   Install bubblewrap (<span class="text-ink">apt install bubblewrap</span>) or Docker
                   on this host before running real submissions.
                 </p>`
              : ""
          }
          <div class="mt-6 grid gap-5 sm:grid-cols-2">
            ${field("round_timeout", "Round timeout (s)", settings.round_timeout, {
              step: "0.1",
              min: 0.1,
            })}
            ${field("mem_mb", "Memory ceiling (MB)", settings.mem_mb, { min: 64 })}
            ${field("submit_cooldown", "Submit cooldown (s)", settings.submit_cooldown, { min: 0 })}
          </div>
          <p class="mt-4 font-mono text-[10px] leading-relaxed text-ink-3">
            The problem statement asks participants to stay under 100 MB. The enforced ceiling is
            deliberately higher — importing numpy and pandas alone costs most of that, and a false
            disqualification is far worse than a generous limit.
          </p>
        </div>
      </div>
    </div>`;
}

function fieldTab(submissions, counts, settings) {
  const banned = new Set((settings.banned_rolls || []).map((r) => r.toUpperCase()));
  const live = new Set((settings.variations || []).map(Number));

  return `
    <div class="panel">
      ${panelHead(
        `Active submissions — ${counts.participants} participants, ${submissions.length} files`
      )}
      <div class="hair-b flex flex-wrap gap-2 px-6 py-4">
        ${ALL_VARIATIONS.map(
          (id) =>
            `<span class="tag ${live.has(id) ? "" : "opacity-40"}">
               ${VARIATION_META[id].index} · ${counts.per_variation?.[id] || 0}${
              live.has(id) ? "" : " · off"
            }
             </span>`
        ).join("")}
      </div>

      <div class="max-h-[30rem] overflow-y-auto">
        ${
          submissions.length
            ? submissions
                .map(
                  (row) => `
          <div class="hair-b flex items-center gap-4 px-6 py-3 last:border-b-0">
            <span class="w-24 shrink-0 font-mono text-sm ${
              banned.has(row.roll) ? "text-loss line-through" : ""
            }">${esc(row.roll)}</span>
            <span class="tag py-0 ${live.has(Number(row.variation)) ? "" : "opacity-40"}">
              V${esc(row.variation)}
            </span>
            <span class="min-w-0 flex-1 truncate text-xs text-ink-2">${esc(row.name || row.email)}</span>
            <span class="hidden font-mono text-[10px] text-ink-3 sm:block">
              ${esc(relativeTime(row.created_at))}
            </span>
            <button data-ban="${esc(row.roll)}" data-banned="${banned.has(row.roll)}"
                    class="border px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.16em]
                           transition-colors ${
                             banned.has(row.roll)
                               ? "border-line-2 text-gain hover:border-gain"
                               : "border-line-2 text-loss hover:border-loss"
                           }">
              ${banned.has(row.roll) ? "Unban" : "Ban"}
            </button>
          </div>`
                )
                .join("")
            : `<p class="px-6 py-16 text-center font-mono text-sm text-ink-3">No submissions yet.</p>`
        }
      </div>
    </div>`;
}

function siteTab(settings) {
  return `
    <div class="grid gap-6 lg:grid-cols-2">
      <div class="panel">
        ${panelHead("Announcement", "A banner at the top of every page, for everyone. Blank hides it.")}
        <div class="p-6">
          <label class="block">
            <span class="label">Message</span>
            <input class="field mt-3" type="text" name="announcement"
                   value="${esc(settings.announcement || "")}"
                   placeholder="Mock auction 1 results are out — variations 3 and 4 are now open.">
          </label>
          <div class="mt-5 flex flex-wrap gap-3">
            <button class="btn-solid" data-save-announcement>Publish</button>
            ${settings.announcement ? `<button class="btn-line" data-clear-announcement>Clear</button>` : ""}
          </div>
        </div>
      </div>

      <div class="panel">
        ${panelHead("Deadline", "Drives the countdown line on the home page and the calendar entry.")}
        <div class="p-6">
          <label class="block">
            <span class="label">Final submission deadline</span>
            <input class="field mt-3" type="datetime-local" name="deadline_iso"
                   value="${esc(toLocalInput(settings.deadline_iso))}">
          </label>
          <p class="mt-3 font-mono text-[10px] text-ink-3">
            currently ${esc(formatDeadline(settings.deadline_iso) || "not set")}
          </p>
          <button class="btn-solid mt-5" data-save-deadline>Save deadline</button>
        </div>
      </div>

      <div class="panel lg:col-span-2">
        ${panelHead(
          "Submission form",
          "The Google Form or Drive link from problem statement §10. Shown on the problem statement " +
            "and the submit page when it is set; hidden when it is blank."
        )}
        <div class="p-6">
          <label class="block">
            <span class="label">Form URL</span>
            <input class="field mt-3" type="url" name="submission_form_url"
                   value="${esc(settings.submission_form_url || "")}"
                   placeholder="https://forms.gle/…">
          </label>
          <button class="btn-solid mt-5" data-save-form>Save link</button>
        </div>
      </div>
    </div>`;
}

function historyTab(showdowns, audit) {
  return `
    <div class="grid gap-6 lg:grid-cols-2">
      <div class="panel">
        ${panelHead("Showdowns")}
        <div class="max-h-[26rem] overflow-y-auto p-6">
          ${
            showdowns.length
              ? showdowns
                  .map(
                    (row) => `
            <div class="panel-2 mb-2 px-4 py-3">
              <div class="flex items-center justify-between font-mono text-[11px]">
                <span class="${
                  row.status === "done"
                    ? "text-gain"
                    : row.status === "running"
                      ? "text-flame"
                      : "text-loss"
                }">#${row.id} ${esc(row.status)}</span>
                <span class="text-ink-3">${esc(relativeTime(row.started_at))}</span>
              </div>
              <p class="mt-2 font-mono text-[10px] text-ink-2">
                ${row.games} games${
                  row.finished_at ? ` · ${Math.round(row.finished_at - row.started_at)}s` : ""
                }
              </p>
              ${row.error ? `<p class="mt-2 font-mono text-[10px] text-loss">${esc(row.error)}</p>` : ""}
            </div>`
                  )
                  .join("")
              : `<p class="py-12 text-center font-mono text-sm text-ink-3">Nothing yet.</p>`
          }
        </div>
      </div>

      <div class="panel">
        ${panelHead("Audit log")}
        <div class="max-h-[26rem] space-y-2 overflow-y-auto p-6 font-mono text-[10px]">
          ${audit
            .map(
              (row) => `
            <div class="hair-b flex gap-3 pb-2">
              <span class="w-16 shrink-0 text-ink-3">${esc(relativeTime(row.at))}</span>
              <span class="w-20 shrink-0 text-flame">${esc(row.action)}</span>
              <span class="min-w-0 flex-1 truncate text-ink-2">${esc(row.actor)} ${esc(row.detail)}</span>
            </div>`
            )
            .join("")}
        </div>
      </div>
    </div>`;
}

// --- ISO <-> <input type="datetime-local"> -------------------------------------

function toLocalInput(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const pad = (n) => String(n).padStart(2, "0");
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  );
}

function fromLocalInput(value) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toISOString();
}

// --- page ----------------------------------------------------------------------

export async function renderAdmin(app) {
  if (!store.me.signed_in) {
    navigate("/login", { replace: true });
    return;
  }
  if (!store.me.is_admin) {
    app.innerHTML = `
      <section class="bleed py-32">
        <p class="label text-loss">Error 403</p>
        <h1 class="d1 mt-8 font-display">Admins<br>only</h1>
        <p class="mt-8 text-sm text-ink-2">This account is not on the admin list.</p>
        <a href="/" data-link class="btn-line mt-10">Back to the floor</a>
      </section>`;
    return;
  }

  let firstPaint = true;

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

  const paint = () => {
    const { settings, schedule, counts, isolation, submissions, showdowns, audit } = data;

    app.innerHTML = `
      <section class="bleed py-14">
        <div class="flex flex-wrap items-end justify-between gap-6">
          <div>
            <span class="tag">Control room</span>
            <h1 class="d2 mt-6 font-display">Competition controls</h1>
            <p class="mt-4 max-w-xl text-sm leading-relaxed text-ink-2">
              Switches and presets save the moment you click them and are pushed to every open
              browser. Text and number fields need the save button underneath them.
            </p>
          </div>
          <button class="btn-line" data-refresh>Refresh</button>
        </div>

        <div class="hair-b mt-10 flex flex-wrap gap-1">
          ${TABS.map(
            ([id, label]) => `
            <button data-tab="${id}"
                    class="-mb-px border-b-2 px-4 py-3 font-mono text-[11px] uppercase tracking-[0.16em]
                           transition-colors ${
                             tab === id
                               ? "border-flame text-ink"
                               : "border-transparent text-ink-3 hover:text-ink"
                           }">${label}</button>`
          ).join("")}
        </div>

        <div class="mt-8">
          ${
            tab === "showdown"
              ? showdownTab(settings, schedule, counts)
              : tab === "game"
                ? gameTab(settings, counts)
                : tab === "secrets"
                  ? secretsTab(settings, isolation)
                  : tab === "field"
                    ? fieldTab(submissions, counts, settings)
                    : tab === "site"
                      ? siteTab(settings)
                      : historyTab(showdowns, audit)
          }
        </div>

        ${
          ["showdown", "game", "secrets"].includes(tab)
            ? `<div class="mt-8 flex flex-wrap items-center gap-4">
                 <button class="btn-solid" data-save>Save the fields above</button>
                 <span class="font-mono text-[10px] text-ink-3">
                   Switches, intervals and grouping have already saved.
                 </span>
               </div>`
            : ""
        }
      </section>`;

    wire();

    if (!firstPaint) revealAll(app);
    firstPaint = false;
  };

  const numeric = new Set([
    "interval_minutes", "num_rounds", "block_size", "group_size", "iterations",
    "finals_size", "workers", "mem_mb", "seed", "submit_cooldown",
  ]);
  const floaty = new Set([
    "round_timeout", "kappa_lo", "kappa_hi", "jitter_lo", "jitter_hi", "floor_fraction",
  ]);

  const collect = () => {
    const changes = {};
    app.querySelectorAll("input[name]").forEach((input) => {
      const key = input.name;
      if (numeric.has(key)) {
        const value = parseInt(input.value, 10);
        if (Number.isFinite(value)) changes[key] = value;
      } else if (floaty.has(key)) {
        const value = parseFloat(input.value);
        if (Number.isFinite(value)) changes[key] = value;
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

  /** Live arithmetic for the capital draw, so the numbers are not abstract. */
  const paintCapitalPreview = () => {
    const node = app.querySelector("[data-capital-preview]");
    if (!node) return;
    const read = (key, fallback) => {
      const input = app.querySelector(`input[name="${key}"]`);
      const value = parseFloat(input?.value);
      return Number.isFinite(value) ? value : fallback;
    };
    const kappaLo = read("kappa_lo", 0.5);
    const kappaHi = read("kappa_hi", 2.5);
    const jitterLo = read("jitter_lo", -10);
    const jitterHi = read("jitter_hi", 10);
    const floor = read("floor_fraction", 0.05);

    const M = 100;
    const low = Math.max(kappaLo * M + jitterLo, floor * M);
    const high = kappaHi * M + jitterHi;
    node.textContent =
      `With a block maximum of ${M}, starting capital lands between ` +
      `${low.toFixed(1)} and ${high.toFixed(1)} — ` +
      `${(low / M).toFixed(2)}× to ${(high / M).toFixed(2)}× the hidden maximum.` +
      (kappaHi < kappaLo ? "  ⚠ κ maximum is below κ minimum." : "");
  };

  const wire = () => {
    applyBarWidths(app);
    paintCapitalPreview();

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

    app.querySelectorAll("[data-grouping]").forEach((button) =>
      button.addEventListener("click", () => save({ grouping: button.dataset.grouping }))
    );

    app.querySelectorAll("[data-variation-toggle]").forEach((button) =>
      button.addEventListener("click", () => {
        const id = Number(button.dataset.variationToggle);
        const current = new Set((data.settings.variations || []).map(Number));
        if (current.has(id)) current.delete(id);
        else current.add(id);
        if (!current.size) {
          toast("At least one variation has to stay released.", "error");
          return;
        }
        save({ variations: [...current].sort((a, b) => a - b) });
      })
    );

    app.querySelectorAll('input[name^="kappa"], input[name^="jitter"], input[name="floor_fraction"]')
      .forEach((input) => input.addEventListener("input", paintCapitalPreview));

    app.querySelector("[data-save]")?.addEventListener("click", () => save(collect()));

    app.querySelector("[data-save-announcement]")?.addEventListener("click", () => {
      const input = app.querySelector('input[name="announcement"]');
      save({ announcement: input.value.trim() });
    });

    app.querySelector("[data-clear-announcement]")?.addEventListener("click", () =>
      save({ announcement: "" })
    );

    app.querySelector("[data-save-form]")?.addEventListener("click", () => {
      const input = app.querySelector('input[name="submission_form_url"]');
      save({ submission_form_url: input.value.trim() });
    });

    app.querySelector("[data-save-deadline]")?.addEventListener("click", () => {
      const input = app.querySelector('input[name="deadline_iso"]');
      const iso = fromLocalInput(input.value);
      if (input.value && !iso) {
        toast("That is not a date the browser understood.", "error");
        return;
      }
      save({ deadline_iso: iso });
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

  // The clock keeps moving while this page is open. Repaint for it, but never
  // while somebody is typing into one of these fields — a showdown finishing
  // mid-edit must not swallow what they were entering.
  let signature = "";
  const unsubscribe = store.subscribe(() => {
    if (!data || tab !== "showdown") return;
    if (app.contains(document.activeElement) && document.activeElement?.tagName === "INPUT") return;

    const schedule = store.schedule;
    const next = JSON.stringify([
      schedule.running,
      schedule.next_run_at,
      schedule.last_run_at,
      schedule.progress_done,
    ]);
    if (next === signature) return;
    signature = next;

    data.schedule = schedule;
    paint();
  });

  return unsubscribe;
}
