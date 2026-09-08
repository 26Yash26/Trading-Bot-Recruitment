// The showdown clock.
//
// `next_run_at` is an absolute server timestamp, and the browser's clock is not
// trustworthy — a laptop three minutes fast would show a countdown three minutes
// short. So the offset between the two clocks is measured once from `/api/state`
// and every tick is computed against the corrected time.

import { clockParts, esc } from "./ui.js";

let clockOffset = 0; // serverNow - browserNow, in seconds

export function syncClock(serverNow) {
  if (typeof serverNow === "number" && serverNow > 0) {
    clockOffset = serverNow - Date.now() / 1000;
  }
}

export const serverNow = () => Date.now() / 1000 + clockOffset;

const SIZES = {
  lg: "d2",
  md: "d3",
  sm: "text-3xl",
};

function digit(key, caption, size) {
  return `
    <div>
      <span class="block font-display ${size} tabular-nums leading-none" data-clock-${key}>--</span>
      <span class="label mt-3 block">${caption}</span>
    </div>`;
}

/**
 * The clock's markup. `label` names what is being counted down to; `size`
 * picks how loud it is — the hero uses `lg`, the sidebars `sm`.
 */
export function renderCountdown({ label = "Next showdown", size = "md" } = {}) {
  const digits = SIZES[size] || SIZES.md;
  const gap = `<span class="font-display ${digits} leading-none text-ink-3">:</span>`;

  return `
    <div data-countdown>
      <div class="flex items-center justify-between gap-3">
        <p class="label">${esc(label)}</p>
        <span class="tag" data-clock-state>
          <span class="dot" data-clock-dot></span>
          <span data-clock-state-text>sync</span>
        </span>
      </div>

      <div class="mt-6 flex items-start gap-3 md:gap-4" data-clock-digits>
        ${digit("h", "hrs", digits)}
        ${gap}
        ${digit("m", "min", digits)}
        ${gap}
        ${digit("s", "sec", digits)}
      </div>

      <p class="mt-6 hidden font-display ${digits} leading-none" data-clock-banner></p>

      <div class="bar-track mt-7">
        <div class="bar bg-flame" data-clock-bar></div>
      </div>
      <p class="mt-3 font-mono text-[11px] text-ink-3" data-clock-note>syncing…</p>
    </div>`;
}

/**
 * Drive a rendered countdown. Returns a stop function.
 * `getSchedule()` must return the latest `/api/state` schedule block.
 */
export function attachCountdown(root, getSchedule, { onElapsed } = {}) {
  const el = {
    h: root.querySelector("[data-clock-h]"),
    m: root.querySelector("[data-clock-m]"),
    s: root.querySelector("[data-clock-s]"),
    digits: root.querySelector("[data-clock-digits]"),
    banner: root.querySelector("[data-clock-banner]"),
    bar: root.querySelector("[data-clock-bar]"),
    note: root.querySelector("[data-clock-note]"),
    state: root.querySelector("[data-clock-state]"),
    stateText: root.querySelector("[data-clock-state-text]"),
  };
  if (!el.h || !el.bar) return () => {};

  // Assigned here rather than in the stylesheet: the bar is also used for
  // static charts, and only the clock wants a one-second glide.
  el.bar.style.transition = "width 0.95s linear";

  const showBanner = (text) => {
    el.banner.textContent = text;
    el.banner.classList.remove("hidden");
    el.digits.classList.add("hidden");
  };

  const showDigits = () => {
    el.banner.classList.add("hidden");
    el.digits.classList.remove("flex", "hidden");
    el.digits.classList.add("flex");
  };

  const setState = (text, kind) => {
    el.stateText.textContent = text;
    el.state.className = kind === "live" ? "tag tag-live" : "tag";
  };

  let firedAt = 0;

  const tick = () => {
    const schedule = getSchedule() || {};
    const nextAt = Number(schedule.next_run_at) || 0;
    const intervalSeconds = Math.max(60, (Number(schedule.interval_minutes) || 120) * 60);

    if (schedule.running) {
      const { progress_done: done = 0, progress_total: total = 0 } = schedule;
      showBanner("Playing");
      setState("live", "live");
      el.note.textContent = total ? `game ${done} of ${total}` : "the field is playing…";
      el.bar.style.width = total ? `${Math.round((done / total) * 100)}%` : "100%";
      return;
    }

    if (!schedule.enabled) {
      showBanner("Paused");
      setState("paused");
      el.note.textContent = "the organisers have frozen the board";
      el.bar.style.width = "0%";
      return;
    }

    showDigits();

    if (!nextAt) {
      el.h.textContent = "--";
      el.m.textContent = "--";
      el.s.textContent = "--";
      setState("idle");
      el.note.textContent = "waiting for the first run";
      el.bar.style.width = "0%";
      return;
    }

    const { hours, minutes, seconds, total } = clockParts(nextAt - serverNow());
    el.h.textContent = hours;
    el.m.textContent = minutes;
    el.s.textContent = seconds;

    const elapsed = 1 - Math.min(1, total / intervalSeconds);
    el.bar.style.width = `${Math.round(elapsed * 100)}%`;

    if (total <= 0) {
      setState("due", "live");
      el.note.textContent = "starting…";
      // The scheduler needs a moment to flip `running`; ask again once, not every second.
      if (onElapsed && serverNow() - firedAt > 20) {
        firedAt = serverNow();
        onElapsed();
      }
    } else if (total < 60) {
      setState("armed", "live");
      el.note.textContent = "bots are lining up";
    } else {
      setState("armed");
      el.note.textContent = `at ${new Date(nextAt * 1000).toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      })}`;
    }
  };

  tick();
  const timer = setInterval(tick, 1000);
  return () => clearInterval(timer);
}
