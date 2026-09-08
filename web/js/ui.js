// Small DOM helpers shared by every page.
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
    hours: String(Math.floor(total / 3600)).padStart(2, "0"),
    minutes: String(Math.floor((total % 3600) / 60)).padStart(2, "0"),
    seconds: String(total % 60).padStart(2, "0"),
    total,
  };
}

const TOAST_STYLES = {
  ok: "border-gain/45 text-gain",
  error: "border-loss/45 text-loss",
  info: "border-gold/45 text-gold",
};

export function toast(message, kind = "info", ttl = 5200) {
  const host = document.getElementById("toasts");
  if (!host) return;

  const node = document.createElement("div");
  node.className =
    `pointer-events-auto animate-rise rounded-xl border bg-surface/95 px-4 py-3 text-sm ` +
    `shadow-2xl backdrop-blur ${TOAST_STYLES[kind] ?? TOAST_STYLES.info}`;
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

/** Count a number up to its target — used on the hero stat tiles. */
export function animateNumber(el, to, { digits = 0, duration = 900 } = {}) {
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) {
    el.textContent = Number(to).toFixed(digits);
    return;
  }
  const from = Number(el.dataset.value || 0);
  const start = performance.now();
  const step = (now) => {
    const t = Math.min(1, (now - start) / duration);
    const eased = 1 - Math.pow(1 - t, 3);
    el.textContent = (from + (to - from) * eased).toFixed(digits);
    if (t < 1) requestAnimationFrame(step);
    else el.dataset.value = String(to);
  };
  requestAnimationFrame(step);
}

/** Reveal elements as they scroll into view. */
export function observeReveals(root = document) {
  const targets = $$("[data-reveal]", root);
  if (!targets.length) return;

  if (matchMedia("(prefers-reduced-motion: reduce)").matches) {
    targets.forEach((el) => el.classList.add("opacity-100"));
    return;
  }

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        const delay = Number(entry.target.dataset.reveal) || 0;
        entry.target.style.animationDelay = `${delay}ms`;
        entry.target.classList.add("animate-rise", "opacity-100");
        observer.unobserve(entry.target);
      });
    },
    { threshold: 0.12, rootMargin: "0px 0px -40px 0px" }
  );
  targets.forEach((el) => {
    el.classList.add("opacity-0");
    observer.observe(el);
  });
}

export const VARIATION_META = {
  1: { name: "Own Value", formula: "xᵢ − bid", accent: "text-gold", ring: "border-gold/40" },
  2: { name: "Field Max", formula: "X − bid", accent: "text-cyan", ring: "border-cyan/40" },
  3: { name: "Runner-up Tax", formula: "X − bid, 2nd pays ½", accent: "text-violet", ring: "border-violet/40" },
};
