// Scroll choreography: the reveals, the counters, the pointer ring.
//
// One IntersectionObserver drives every reveal on the page. The CSS owns what a
// reveal *looks* like (`[data-reveal]` in app.css); this file only decides when
// it happens, and guarantees that nothing stays hidden if the observer never
// fires — a section that never un-hides is worse than one that never animates.

const reduced = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

/**
 * Watch every `[data-reveal]` under `root` and add `.is-in` as it arrives.
 * Returns a teardown function.
 */
export function observeReveals(root = document) {
  const targets = [...root.querySelectorAll("[data-reveal]")];
  if (!targets.length) return () => {};

  if (reduced()) {
    targets.forEach((el) => el.classList.add("is-in"));
    return () => {};
  }

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        const delay = Number(entry.target.dataset.reveal) || 0;
        setTimeout(() => entry.target.classList.add("is-in"), delay);
        observer.unobserve(entry.target);
      });
    },
    { threshold: 0.08, rootMargin: "0px 0px -10% 0px" }
  );
  targets.forEach((el) => observer.observe(el));

  // Belt and braces: whatever happens, the page is readable a second later.
  const failsafe = setTimeout(() => targets.forEach((el) => el.classList.add("is-in")), 2200);

  return () => {
    clearTimeout(failsafe);
    observer.disconnect();
  };
}

/**
 * Mark everything under `root` as already revealed.
 *
 * A page that repaints on live data builds new `[data-reveal]` nodes after the
 * router's observer has been set up, so nothing is watching them — and the CSS
 * starts them hidden. Re-animating on every leaderboard tick would also be
 * unbearable, so a repaint simply shows its content at once.
 */
export function revealAll(root = document) {
  root.querySelectorAll("[data-reveal]").forEach((el) => el.classList.add("is-in"));
}

/** Count `[data-count]` elements up to their target once they are on screen. */
export function observeCounters(root = document) {
  const targets = [...root.querySelectorAll("[data-count]")];
  if (!targets.length) return () => {};

  const paint = (el) => {
    const to = Number(el.dataset.count) || 0;
    const digits = Number(el.dataset.countDigits) || 0;
    if (reduced()) {
      el.textContent = to.toFixed(digits);
      return;
    }
    const start = performance.now();
    const step = (now) => {
      const t = Math.min(1, (now - start) / 1100);
      const eased = 1 - Math.pow(1 - t, 4);
      el.textContent = (to * eased).toFixed(digits);
      if (t < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  };

  const painted = new WeakSet();
  const run = (el) => {
    if (painted.has(el)) return;
    painted.add(el);
    paint(el);
  };

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        run(entry.target);
        observer.unobserve(entry.target);
      });
    },
    { threshold: 0.4 }
  );
  targets.forEach((el) => observer.observe(el));

  // Same guarantee as the reveals: a counter that never animates is a bug, but
  // a counter stuck reading zero is a wrong number on the front page.
  const failsafe = setTimeout(() => targets.forEach(run), 2200);

  return () => {
    clearTimeout(failsafe);
    observer.disconnect();
  };
}

/**
 * Elements marked `[data-drift="0.15"]` move against the scroll by that factor.
 * One rAF loop for the whole page, and only while something is in view.
 */
export function startParallax() {
  if (reduced()) return () => {};

  let frame = null;
  const tick = () => {
    frame = null;
    const middle = window.innerHeight / 2;
    document.querySelectorAll("[data-drift]").forEach((el) => {
      const rect = el.getBoundingClientRect();
      if (rect.bottom < -200 || rect.top > window.innerHeight + 200) return;
      const offset = (rect.top + rect.height / 2 - middle) * (Number(el.dataset.drift) || 0);
      el.style.transform = `translate3d(0, ${offset.toFixed(1)}px, 0)`;
    });
  };
  const onScroll = () => {
    if (frame === null) frame = requestAnimationFrame(tick);
  };

  tick();
  window.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("resize", onScroll, { passive: true });
  return () => {
    if (frame !== null) cancelAnimationFrame(frame);
    window.removeEventListener("scroll", onScroll);
    window.removeEventListener("resize", onScroll);
  };
}

/**
 * A ring that trails the pointer and swells over anything clickable.
 *
 * The real cursor is deliberately left visible — hiding it is the house style
 * on sites like this, and it is also the fastest way to make a form feel broken.
 * Never shown to a coarse pointer, which has no cursor to trail.
 */
export function startCursor() {
  const ring = document.querySelector("[data-cursor-ring]");
  if (!ring || !matchMedia("(pointer: fine)").matches || reduced()) return () => {};

  ring.classList.remove("hidden");

  let targetX = window.innerWidth / 2;
  let targetY = window.innerHeight / 2;
  let x = targetX;
  let y = targetY;
  let raf = null;

  const HOT = 'a, button, input, label, select, textarea, [role="tab"], [data-link]';

  const onMove = (event) => {
    targetX = event.clientX;
    targetY = event.clientY;
    ring.dataset.hot = String(Boolean(event.target.closest?.(HOT)));
  };
  const onLeave = () => ring.style.setProperty("opacity", "0");
  const onEnter = () => ring.style.setProperty("opacity", "1");

  const loop = () => {
    x += (targetX - x) * 0.18;
    y += (targetY - y) * 0.18;
    ring.style.transform = `translate3d(${x.toFixed(1)}px, ${y.toFixed(1)}px, 0)`;
    raf = requestAnimationFrame(loop);
  };

  window.addEventListener("pointermove", onMove, { passive: true });
  document.addEventListener("pointerleave", onLeave);
  document.addEventListener("pointerenter", onEnter);
  loop();

  return () => {
    if (raf !== null) cancelAnimationFrame(raf);
    window.removeEventListener("pointermove", onMove);
    document.removeEventListener("pointerleave", onLeave);
    document.removeEventListener("pointerenter", onEnter);
    ring.classList.add("hidden");
  };
}

/**
 * Wrap a heading's words in the two-element structure the CSS reveal needs.
 *
 * Written as markup it would be unreadable, so it is done here: `lines` is an
 * array of strings, already escaped by the caller.
 */
export function revealLines(lines) {
  return lines
    .map((line) => `<span class="reveal-line"><span>${line}</span></span>`)
    .join("");
}
