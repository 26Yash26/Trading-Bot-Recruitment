// The auction tape drawn in the hero panel.
//
// A stepped chart of the winning bid and the runner-up bid, scrolling right to
// left. The series is generated here, not fetched — per-round bids are not
// published, and pretending otherwise would be a lie on the front page — so the
// panel that holds it is captioned as a sample game.
//
// It reads its colours out of the stylesheet rather than hard-coding them, which
// is what lets the same canvas work in both themes.

import { themeColor } from "./ui.js";

const POINTS = 60;

export function startTape(canvas) {
  if (!canvas || !canvas.getContext) return () => {};

  const ctx = canvas.getContext("2d", { alpha: true });
  const reduced = matchMedia("(prefers-reduced-motion: reduce)");

  let width = 0;
  let height = 0;
  let raf = null;
  let phase = 0;

  // Two correlated random walks in [0.1, 0.95]: the top bid, and a runner-up
  // that trails it. Seeded once and then extended a point at a time.
  let top = seed(0.62);
  let second = top.map((value) => Math.max(0.06, value - 0.08 - Math.random() * 0.16));

  function seed(start) {
    let value = start;
    return Array.from({ length: POINTS }, () => {
      value = clamp(value + (Math.random() - 0.5) * 0.16, 0.12, 0.95);
      return value;
    });
  }

  function clamp(value, low, high) {
    return Math.min(high, Math.max(low, value));
  }

  function advance() {
    const next = clamp(top[top.length - 1] + (Math.random() - 0.5) * 0.16, 0.12, 0.95);
    top.push(next);
    top.shift();
    second.push(Math.max(0.06, next - 0.06 - Math.random() * 0.18));
    second.shift();
  }

  function resize() {
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    width = canvas.clientWidth;
    height = canvas.clientHeight;
    if (!width || !height) return;
    canvas.width = Math.floor(width * dpr);
    canvas.height = Math.floor(height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  const pointAt = (series, index, step, offset) => ({
    x: index * step - offset,
    y: height - 14 - series[index] * (height - 30),
  });

  function stepPath(series, step, offset) {
    ctx.beginPath();
    for (let i = 0; i < series.length; i += 1) {
      const { x, y } = pointAt(series, i, step, offset);
      if (i === 0) ctx.moveTo(x, y);
      else {
        ctx.lineTo(x, y); // vertical leg first: bids jump, they do not glide
        ctx.lineTo(x + step, y);
      }
    }
  }

  function draw() {
    if (!width || !height) return;

    const rule = themeColor("--color-line", "#21212a");
    const flare = themeColor("--color-flame", "#ff4d17");
    const accent = themeColor("--color-jade", "#3ddbc0");

    const step = width / (POINTS - 8);
    const offset = phase * step;

    ctx.clearRect(0, 0, width, height);

    // Gridlines — four of them, the same spacing a printed chart would use.
    ctx.strokeStyle = rule;
    ctx.lineWidth = 1;
    for (let i = 1; i <= 4; i += 1) {
      const y = Math.round((height / 5) * i) + 0.5;
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
      ctx.stroke();
    }

    // Runner-up: thin and dashed, so the gap to the winner reads as the spread.
    ctx.save();
    ctx.setLineDash([3, 4]);
    ctx.strokeStyle = accent;
    ctx.globalAlpha = 0.7;
    ctx.lineWidth = 1.2;
    stepPath(second, step, offset);
    ctx.stroke();
    ctx.restore();

    // Winning bid, with a wash beneath it.
    stepPath(top, step, offset);
    ctx.save();
    ctx.lineTo(width + step, height);
    ctx.lineTo(-step, height);
    ctx.closePath();
    ctx.globalAlpha = 0.14;
    ctx.fillStyle = flare;
    ctx.fill();
    ctx.restore();

    stepPath(top, step, offset);
    ctx.strokeStyle = flare;
    ctx.lineWidth = 1.8;
    ctx.lineJoin = "round";
    ctx.stroke();

    // The head of the tape.
    const head = pointAt(top, top.length - 1, step, offset);
    ctx.fillStyle = flare;
    ctx.beginPath();
    ctx.arc(Math.min(head.x, width - 4), head.y, 3, 0, Math.PI * 2);
    ctx.fill();
  }

  function frame() {
    phase += 0.012;
    if (phase >= 1) {
      phase -= 1;
      advance();
    }
    draw();
    raf = requestAnimationFrame(frame);
  }

  function stop() {
    if (raf !== null) cancelAnimationFrame(raf);
    raf = null;
  }

  function start() {
    stop();
    if (reduced.matches) draw();
    else raf = requestAnimationFrame(frame);
  }

  const onResize = () => {
    resize();
    draw();
  };
  const onVisibility = () => (document.hidden ? stop() : start());
  const onTheme = () => draw();

  resize();
  start();

  window.addEventListener("resize", onResize, { passive: true });
  document.addEventListener("visibilitychange", onVisibility);
  document.addEventListener("qg:theme", onTheme);
  reduced.addEventListener?.("change", start);

  return () => {
    stop();
    window.removeEventListener("resize", onResize);
    document.removeEventListener("visibilitychange", onVisibility);
    document.removeEventListener("qg:theme", onTheme);
  };
}
