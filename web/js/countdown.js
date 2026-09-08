// The showdown clock.
//
// `next_run_at` is an absolute server timestamp, and the browser's clock is not
// trustworthy — a laptop three minutes fast would show a countdown three minutes
// short. So the offset between the two clocks is measured once from `/api/state`
// and every tick is computed against the corrected time.

import { clockParts } from "./ui.js";

let clockOffset = 0; // serverNow - browserNow, in seconds

export function syncClock(serverNow) {
  if (typeof serverNow === "number" && serverNow > 0) {
    clockOffset = serverNow - Date.now() / 1000;
  }
}

export const serverNow = () => Date.now() / 1000 + clockOffset;

const RING_CIRCUMFERENCE = 2 * Math.PI * 86;

export function renderCountdown() {
  return `
    <div class="relative grid place-items-center" data-countdown>
      <svg viewBox="0 0 200 200" class="h-52 w-52 -rotate-90 md:h-60 md:w-60" aria-hidden="true">
        <circle cx="100" cy="100" r="86" fill="none" stroke="currentColor"
                class="text-line" stroke-width="6"></circle>
        <circle cx="100" cy="100" r="86" fill="none" stroke="url(#ring)" stroke-width="6"
                stroke-linecap="round" data-ring
                stroke-dasharray="${RING_CIRCUMFERENCE}" stroke-dashoffset="${RING_CIRCUMFERENCE}"></circle>
        <defs>
          <linearGradient id="ring" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stop-color="#ffd76a"></stop>
            <stop offset="60%" stop-color="#f5b625"></stop>
            <stop offset="100%" stop-color="#ff9a3c"></stop>
          </linearGradient>
        </defs>
      </svg>

      <div class="absolute inset-0 grid place-items-center text-center">
        <div>
          <p class="font-mono text-[10px] uppercase tracking-[0.28em] text-ink-faint">Next showdown</p>
          <p class="mt-1 font-heading text-4xl font-bold tabular-nums text-ink md:text-5xl" data-clock
             role="timer" aria-live="off">--:--:--</p>
          <p class="mt-1 font-mono text-[11px] text-gold" data-clock-note>syncing…</p>
        </div>
      </div>
    </div>`;
}

/**
 * Drive a rendered countdown. Returns a stop function.
 * `getState()` must return the latest `/api/state` schedule block.
 */
export function attachCountdown(root, getState, { onElapsed } = {}) {
  const clock = root.querySelector("[data-clock]");
  const note = root.querySelector("[data-clock-note]");
  const ring = root.querySelector("[data-ring]");
  if (!clock) return () => {};

  let firedAt = 0;

  const tick = () => {
    const schedule = getState() || {};
    const nextAt = Number(schedule.next_run_at) || 0;
    const intervalSeconds = Math.max(60, (Number(schedule.interval_minutes) || 120) * 60);

    if (schedule.running) {
      const { progress_done: done = 0, progress_total: total = 0 } = schedule;
      clock.textContent = "LIVE";
      clock.classList.add("text-gradient-gold", "animate-flicker");
      note.textContent = total ? `playing game ${done} of ${total}` : "bots are playing…";
      ring.setAttribute("stroke-dashoffset", "0");
      return;
    }

    clock.classList.remove("text-gradient-gold", "animate-flicker");

    if (!schedule.enabled) {
      clock.textContent = "PAUSED";
      note.textContent = "showdowns are paused";
      ring.setAttribute("stroke-dashoffset", String(RING_CIRCUMFERENCE));
      return;
    }
    if (!nextAt) {
      clock.textContent = "--:--:--";
      note.textContent = "waiting for the first run";
      return;
    }

    const remaining = nextAt - serverNow();
    const { hours, minutes, seconds, total } = clockParts(remaining);
    clock.textContent = `${hours}:${minutes}:${seconds}`;

    const elapsedFraction = Math.min(1, Math.max(0, 1 - total / intervalSeconds));
    ring.setAttribute(
      "stroke-dashoffset",
      String(RING_CIRCUMFERENCE * (1 - elapsedFraction))
    );

    if (total <= 0) {
      note.textContent = "starting…";
      // The scheduler needs a moment to flip `running`; ask again once, not every second.
      if (onElapsed && serverNow() - firedAt > 20) {
        firedAt = serverNow();
        onElapsed();
      }
    } else if (total < 60) {
      note.textContent = "bots are lining up";
    } else {
      note.textContent = new Date(nextAt * 1000).toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      });
    }
  };

  tick();
  const timer = setInterval(tick, 1000);
  return () => clearInterval(timer);
}
