// Decorative canvas behind the whole site: a slow auction tape.
//
// Two layers — a drifting "winning bid" line that random-walks across the
// viewport, and faint vertical bid columns that rise and fade. It is purely
// atmospheric, so it yields immediately to `prefers-reduced-motion` and stops
// entirely when the tab is hidden rather than burning a phone battery.

const GOLD = "245, 182, 37";

export function startBackdrop(canvas) {
  if (!canvas || !canvas.getContext) return () => {};

  const ctx = canvas.getContext("2d", { alpha: true });
  const reduced = matchMedia("(prefers-reduced-motion: reduce)");

  let width = 0;
  let height = 0;
  let dpr = 1;
  let columns = [];
  let line = [];
  let frame = 0;
  let raf = null;

  function resize() {
    dpr = Math.min(2, window.devicePixelRatio || 1);
    width = canvas.clientWidth;
    height = canvas.clientHeight;
    canvas.width = Math.floor(width * dpr);
    canvas.height = Math.floor(height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const count = Math.max(14, Math.floor(width / 68));
    columns = Array.from({ length: count }, (_, i) => ({
      x: (i + 0.5) * (width / count),
      value: Math.random() * 0.5 + 0.1,
      target: Math.random() * 0.75 + 0.12,
      speed: Math.random() * 0.006 + 0.002,
    }));

    const points = Math.max(28, Math.floor(width / 34));
    let y = 0.55;
    line = Array.from({ length: points }, () => {
      y = Math.min(0.86, Math.max(0.18, y + (Math.random() - 0.5) * 0.09));
      return y;
    });
  }

  function drawColumns() {
    const base = height * 0.97;
    for (const column of columns) {
      column.value += (column.target - column.value) * column.speed;
      if (Math.abs(column.target - column.value) < 0.015) {
        column.target = Math.random() * 0.78 + 0.1;
      }

      const barHeight = column.value * height * 0.5;
      const gradient = ctx.createLinearGradient(0, base - barHeight, 0, base);
      gradient.addColorStop(0, `rgba(${GOLD}, 0.09)`);
      gradient.addColorStop(1, `rgba(${GOLD}, 0)`);
      ctx.fillStyle = gradient;
      ctx.fillRect(column.x - 9, base - barHeight, 18, barHeight);
    }
  }

  function drawTape(offset) {
    const step = width / (line.length - 1);
    ctx.beginPath();
    line.forEach((value, index) => {
      const x = index * step;
      const wobble = Math.sin((index * 0.7) + offset * 0.6) * 6;
      const y = value * height * 0.72 + height * 0.08 + wobble;
      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });

    ctx.strokeStyle = `rgba(${GOLD}, 0.28)`;
    ctx.lineWidth = 1.4;
    ctx.shadowBlur = 18;
    ctx.shadowColor = `rgba(${GOLD}, 0.32)`;
    ctx.stroke();
    ctx.shadowBlur = 0;
  }

  function tick() {
    frame += 1;
    ctx.clearRect(0, 0, width, height);
    drawColumns();
    drawTape(frame * 0.01);

    // Occasionally the tape re-prints — a new round settling.
    if (frame % 220 === 0) {
      line.shift();
      const last = line[line.length - 1];
      line.push(Math.min(0.86, Math.max(0.18, last + (Math.random() - 0.5) * 0.12)));
    }
    raf = requestAnimationFrame(tick);
  }

  function drawStatic() {
    ctx.clearRect(0, 0, width, height);
    drawColumns();
    drawTape(0);
  }

  function start() {
    stop();
    if (reduced.matches) drawStatic();
    else raf = requestAnimationFrame(tick);
  }

  function stop() {
    if (raf !== null) cancelAnimationFrame(raf);
    raf = null;
  }

  const onResize = () => {
    resize();
    if (reduced.matches) drawStatic();
  };
  const onVisibility = () => (document.hidden ? stop() : start());

  resize();
  start();
  window.addEventListener("resize", onResize, { passive: true });
  document.addEventListener("visibilitychange", onVisibility);
  reduced.addEventListener?.("change", start);

  return () => {
    stop();
    window.removeEventListener("resize", onResize);
    document.removeEventListener("visibilitychange", onVisibility);
  };
}
