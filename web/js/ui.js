// Formatting, escaping, and the four variations. No DOM choreography, that
// lives in motion.js.
//
// Rule for this codebase: markup is built from template strings, and *every*
// value that came from a person (a name, a roll number, a rejection message the
// sandbox produced) goes through `esc` on the way in. Nothing else stops a
// participant from naming themselves `<img onerror=...>`.

export const esc = (value) =>
  String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");

export const $ = (selector, root = document) => root.querySelector(selector);
export const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

// --- numbers -------------------------------------------------------------------

export function signed(value, digits = 2) {
  const n = Number(value) || 0;
  return `${n >= 0 ? "+" : "−"}${Math.abs(n).toFixed(digits)}`;
}

export function money(value, digits = 2) {
  const n = Number(value) || 0;
  return n.toLocaleString("en-IN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function compact(value) {
  const n = Number(value) || 0;
  if (Math.abs(n) >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (Math.abs(n) >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return n.toFixed(0);
}

export const clamp = (value, low, high) => Math.min(high, Math.max(low, value));

export const pad2 = (n) => String(n).padStart(2, "0");

// --- time ----------------------------------------------------------------------

export function relativeTime(epochSeconds) {
  if (!epochSeconds) return "never";
  const delta = Date.now() / 1000 - epochSeconds;
  if (delta < 60) return "just now";
  if (delta < 3600) return `${Math.floor(delta / 60)} min ago`;
  if (delta < 86400) return `${Math.floor(delta / 3600)} h ago`;
  return `${Math.floor(delta / 86400)} d ago`;
}

export function clockParts(seconds) {
  const total = Math.max(0, Math.floor(seconds));
  return {
    days: pad2(Math.floor(total / 86400)),
    hours: pad2(Math.floor(total / 3600)),
    minutes: pad2(Math.floor((total % 3600) / 60)),
    seconds: pad2(total % 60),
    total,
  };
}

/** "16 Sep, 23:59" from an ISO string; empty when the string is missing or junk. */
export function formatDeadline(iso, { withTime = true } = {}) {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString([], {
    day: "2-digit",
    month: "short",
    ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}),
  });
}

/** Whole days from now until `iso`; null when there is no usable deadline. */
export function daysUntil(iso) {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return Math.ceil((date.getTime() - Date.now()) / 86_400_000);
}

export function describeInterval(minutes) {
  const m = Number(minutes) || 0;
  if (m <= 0) return "on demand";
  if (m % 60 === 0) {
    const hours = m / 60;
    return hours === 1 ? "every hour" : `every ${hours} hours`;
  }
  return `every ${m} minutes`;
}

// --- the four variations -------------------------------------------------------

// Class names are written out in full rather than assembled from a colour name:
// Tailwind scans these files as text, and a class it never sees spelled out is a
// class it never generates.
export const VARIATION_META = {
  1: {
    index: "01",
    name: "Private Value",
    kind: "first price",
    formula: "xᵢ − b₁",
    ink: "text-flame",
    edge: "border-flame",
    rule: "bg-flame",
    swatch: "--color-flame",
    short: "Your own draw is the prize.",
    detail:
      "The winner takes their own value minus what they bid; everyone else scores zero. " +
      "The only question is how much of your own surplus you hand over to be sure of winning it.",
    rules: [
      "The winner's payoff is <b>xᵢ − b₁</b>, using the winner's own value.",
      "All other players receive zero payoff.",
      "Tied top bids all win, and each collects the full payoff.",
    ],
  },
  2: {
    index: "02",
    name: "Common Value",
    kind: "first price",
    formula: "X − b₁",
    ink: "text-jade",
    edge: "border-jade",
    rule: "bg-jade",
    swatch: "--color-jade",
    short: "The best draw on the table is the prize.",
    detail:
      "X is the largest value drawn by anyone still solvent that round. Winning is worth exactly " +
      "the same to everyone and nobody is told what that is, so this is a pure bidding contest.",
    rules: [
      "The winner's payoff is <b>X − b₁</b>, where X is the largest value drawn by <i>any active player</i>.",
      "You never see X during the round. Last round's realised X is published to everyone.",
      "Tied top bids all win, and each collects the full payoff.",
    ],
  },
  // Variations 3 and 4 carry style only until they are released. Their names,
  // formulas and rules live in `server/late_variations.js`, which is served from
  // `/api/variations/late.js` and 404s while they are switched off, so nothing
  // about them reaches a browser before mock auction 1. `registerLateVariation`
  // fills these in when that module lands.
  3: {
    index: "03",
    name: "Variation 3",
    kind: "",
    formula: "",
    ink: "text-amber",
    edge: "border-amber",
    rule: "bg-amber",
    swatch: "--color-amber",
    short: "",
    detail: "",
    rules: [],
    sealed: true,
  },
  4: {
    index: "04",
    name: "Variation 4",
    kind: "",
    formula: "",
    ink: "text-iris",
    edge: "border-iris",
    rule: "bg-iris",
    swatch: "--color-iris",
    short: "",
    detail: "",
    rules: [],
    sealed: true,
  },
};

export const ALL_VARIATIONS = [1, 2, 3, 4];

/**
 * Fill in a variation whose copy arrived from `/api/variations/late.js`.
 *
 * Mutates the entry in place rather than replacing it, so the eight modules
 * that already hold a reference to `VARIATION_META` pick the copy up without
 * re-importing anything. `sealed` is cleared, which is how a caller tells the
 * difference between "not released" and "released, copy loaded".
 */
export function registerLateVariation(id, meta) {
  const target = VARIATION_META[id];
  if (!target || !meta) return;
  Object.assign(target, meta, { sealed: false });
}


/**
 * The variations the admin currently has switched on.
 *
 * Everything user-facing goes through this, the home page cards, the
 * leaderboard tabs, the rules, the submit slots, so releasing variation 3 in
 * the control room releases it on the site. Before `/api/state` has landed
 * there is nothing to filter by; after it has, an empty list genuinely means
 * none are in play.
 */
export function enabledVariations(state) {
  if (!state || !Array.isArray(state.variations)) return [...ALL_VARIATIONS];
  return ALL_VARIATIONS.filter((id) => state.variations.map(Number).includes(id));
}

// --- feedback ------------------------------------------------------------------

const TOAST_STYLES = {
  ok: "border-gain text-gain",
  error: "border-loss text-loss",
  info: "border-flame text-flame",
};

export function toast(message, kind = "info", ttl = 5200) {
  const host = document.getElementById("toasts");
  if (!host) return;

  const node = document.createElement("div");
  node.className =
    "pointer-events-auto animate-rise border bg-void-2 px-4 py-3 font-mono text-xs " +
    (TOAST_STYLES[kind] ?? TOAST_STYLES.info);
  node.setAttribute("role", kind === "error" ? "alert" : "status");
  node.textContent = message;
  host.appendChild(node);

  setTimeout(() => {
    node.style.transition = "opacity .35s, transform .35s";
    node.style.opacity = "0";
    node.style.transform = "translateY(8px)";
    setTimeout(() => node.remove(), 360);
  }, ttl);
}

// --- DOM odds and ends ---------------------------------------------------------

/**
 * Apply every `data-bar-width="42"` under `root` as a real width.
 *
 * The Content-Security-Policy has no `'unsafe-inline'` for styles, so a `style`
 * attribute written into a template string is dropped by the browser. Assigning
 * through the CSSOM is a different thing entirely and is allowed, so bar widths
 * are carried as data attributes and applied here after paint.
 */
export function applyBarWidths(root = document) {
  $$("[data-bar-width]", root).forEach((el) => {
    el.style.width = `${clamp(Number(el.dataset.barWidth) || 0, 0, 100)}%`;
  });
}

/** Read a themed colour out of the stylesheet, for canvas and SVG drawing. */
export function themeColor(name, fallback = "#000") {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}
