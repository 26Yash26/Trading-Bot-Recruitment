// Upload a bot. Auth-gated, drag-and-drop, with the sandbox's verdict shown inline.

import { api } from "../api.js";
import { navigate, store } from "../main.js";
import { revealAll, revealLines } from "../motion.js";
import { VARIATION_META, enabledVariations, esc, relativeTime, signed, toast } from "../ui.js";

const FILENAME_RE = /^([A-Z]{2}\d{2}[A-Z]\d{3})_([1-9])\.py$/i;

function slotCard(id, submissions) {
  const meta = VARIATION_META[id];
  const active = submissions.find((row) => row.variation === id && row.active);
  const lastAttempt = submissions.find((row) => row.variation === id);

  return `
    <div class="panel p-6">
      <div class="flex items-start justify-between gap-4">
        <span class="font-display text-[2rem] leading-none text-line-2">${meta.index}</span>
        <span class="font-mono text-[10px] uppercase tracking-[0.18em] ${
          active ? "text-gain" : "text-ink-3"
        }">${active ? "● in play" : "○ empty"}</span>
      </div>
      <p class="d4 mt-5 font-display">${esc(meta.name)}</p>
      <p class="mt-3 font-mono text-[11px] text-ink-3">
        ${
          active
            ? `${esc(active.filename)} · ${esc(relativeTime(active.created_at))}`
            : lastAttempt
              ? `last attempt rejected ${esc(relativeTime(lastAttempt.created_at))}`
              : "nothing submitted yet"
        }
      </p>
    </div>`;
}

function historyList(submissions, variations) {
  if (!submissions?.length) {
    return `<p class="px-6 py-12 text-center font-mono text-sm text-ink-3">Nothing submitted yet.</p>`;
  }

  return submissions
    .map((row) => {
      const accepted = row.status === "accepted";
      const meta = VARIATION_META[row.variation];
      return `
        <div class="hair-b flex items-start gap-4 px-6 py-4 last:border-b-0">
          <span class="mt-1.5 h-2 w-2 shrink-0 ${accepted ? "bg-gain" : "bg-loss"}"></span>
          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-2">
              <span class="font-mono text-sm">${esc(row.filename)}</span>
              <span class="tag py-0 ${meta?.edge || ""} ${meta?.ink || ""}">V${esc(row.variation)}</span>
              ${
                row.active && variations.includes(row.variation)
                  ? `<span class="tag border-gain py-0 text-gain">In play</span>`
                  : row.active
                    ? `<span class="tag py-0">V${esc(row.variation)} not released</span>`
                    : ""
              }
            </div>
            ${
              row.message
                ? `<p class="mt-2 text-xs leading-relaxed text-loss">${esc(row.message)}</p>`
                : `<p class="mt-2 font-mono text-[11px] text-ink-3">
                     smoke test net profit ${signed(row.smoke_profit)}
                   </p>`
            }
          </div>
          <span class="shrink-0 font-mono text-[10px] text-ink-3">${esc(relativeTime(row.created_at))}</span>
        </div>`;
    })
    .join("");
}

function verdictCard(result) {
  if (!result) return "";

  if (!result.ok) {
    return `
      <div class="panel mt-6 animate-rise border-l-2 border-l-loss p-6">
        <p class="d4 font-display text-loss">Rejected</p>
        <p class="mt-4 text-sm leading-relaxed">${esc(result.message)}</p>
        <p class="mt-4 font-mono text-[11px] text-ink-3">
          Fix it and upload again, there is no penalty for retrying.
        </p>
      </div>`;
  }

  const { smoke } = result;
  return `
    <div class="panel mt-6 animate-rise border-l-2 border-l-gain p-6">
      <p class="d4 font-display text-gain">Accepted</p>
      <p class="mt-4 text-sm">
        ${esc(result.roll)} · variation ${esc(result.variation)} is in the next showdown.
      </p>
      <dl class="mt-6 grid grid-cols-2 gap-5 sm:grid-cols-4">
        ${[
          ["Smoke net profit", signed(smoke.net_profit)],
          ["Rounds won", smoke.wins],
          ["Errors", smoke.errors],
          ["Timeouts", smoke.timeouts],
        ]
          .map(
            ([label, value]) => `
          <div>
            <dt class="label">${label}</dt>
            <dd class="mt-2 font-mono text-sm">${esc(value)}</dd>
          </div>`
          )
          .join("")}
      </dl>
      <p class="mt-5 font-mono text-[11px] leading-relaxed text-ink-3">
        A short game against the sample bots on stand-in bounds, a sanity check, not a ranking.
        The real distribution is hidden.
      </p>
    </div>`;
}

export async function renderSubmit(app) {
  if (!store.me.signed_in) {
    navigate("/login", { replace: true });
    return;
  }

  let result = null;
  let busy = false;
  let firstPaint = true;

  const paint = () => {
    const state = store.state || {};
    const variations = enabledVariations(state);
    const open = state.submissions_open !== false && variations.length > 0;
    const roll = store.me.roll || "";
    const submissions = store.me.submissions || [];
    const formUrl = (state.submission_form_url || "").trim();

    app.innerHTML = `
      <section class="bleed pt-14 pb-10" data-reveal>
        <span class="tag" data-fade>Signed in as ${esc(store.me.email)}</span>
        <h1 class="d1 mt-8 font-display">${revealLines(["Submit", "your bot"])}</h1>
        <p class="lede mt-10 max-w-2xl" data-fade>
          One file per variation, named
          <code class="font-mono text-flame">${esc(roll || "ROLLNO")}_&lt;variation&gt;.py</code>.
          It is checked the moment you upload it, static policy first, then a short game against the
          sample bots, and you get the verdict right here.
        </p>

        ${
          variations.length === 0
            ? `<div class="panel mt-8 border-l-2 border-l-loss p-5 text-sm" data-fade>
                 Every variation is switched off, so nothing can be submitted at the moment.
               </div>`
            : state.submissions_open === false
              ? `<div class="panel mt-8 border-l-2 border-l-loss p-5 text-sm" data-fade>
                   Submissions are currently closed.
                 </div>`
              : ""
        }
      </section>

      ${
        variations.length
          ? `<div class="bleed pb-10">
               <div class="grid gap-5 sm:grid-cols-2 xl:grid-cols-4" data-reveal>
                 ${variations.map((id) => slotCard(id, submissions)).join("")}
               </div>
             </div>`
          : ""
      }

      <div class="bleed grid gap-10 pb-24 lg:grid-cols-[1.05fr_1fr]" data-reveal>
        <div>
          <label for="botfile"
                 class="panel group grid cursor-pointer place-items-center border-2 border-dashed
                        border-line-2 px-6 py-20 text-center transition-colors hover:border-flame
                        ${open ? "" : "pointer-events-none opacity-40"}"
                 data-drop>
            <input id="botfile" type="file" accept=".py,text/x-python" class="sr-only" ${open ? "" : "disabled"}>
            <span class="grid h-14 w-14 place-items-center border border-line-2 font-mono text-xl
                         transition-transform group-hover:-translate-y-1">↑</span>
            <span class="d4 mt-6 font-display" data-filename>Drop your .py file here</span>
            <span class="mt-3 font-mono text-[11px] text-ink-3">or click to choose · max 512 KB</span>
          </label>

          <button class="btn-solid mt-5 w-full" data-upload ${open ? "" : "disabled"} disabled>
            Run the checks and submit
          </button>

          <div data-verdict>${verdictCard(result)}</div>
        </div>

        <div>
          <h2 class="d4 font-display">Your submissions</h2>
          <div class="panel mt-5 max-h-[24rem] overflow-y-auto">
            ${historyList(submissions, variations)}
          </div>

          <div class="panel mt-6 p-6">
            <h3 class="d4 font-display">What gets checked</h3>
            <ul class="mt-5 space-y-3 text-xs leading-relaxed text-ink-2">
              <li class="flex gap-3"><span class="text-flame">▸</span><span>The filename matches your
                  roll number and a variation that is in play.</span></li>
              <li class="flex gap-3"><span class="text-flame">▸</span><span>The file defines a class
                  <code class="font-mono text-flame">Bot</code> with
                  <code class="font-mono text-flame">get_bid</code>.</span></li>
              <li class="flex gap-3"><span class="text-flame">▸</span><span>No imports outside the
                  numeric stack, no <code class="font-mono">eval</code>,
                  <code class="font-mono">open</code> or interpreter introspection.</span></li>
              <li class="flex gap-3"><span class="text-flame">▸</span><span>A short game against the
                  sample bots: it must not crash, time out or go bankrupt.</span></li>
            </ul>
            ${
              formUrl
                ? `<p class="hair mt-6 pt-5 font-mono text-[11px] leading-relaxed text-ink-3">
                     The official submission of record is the Drive folder linked from the
                     <a href="${esc(formUrl)}" target="_blank" rel="noopener noreferrer"
                        class="link">submission form ↗</a>. This page is the practice board.
                   </p>`
                : ""
            }
          </div>
        </div>
      </div>`;

    wire(open, variations, roll);

    if (!firstPaint) revealAll(app);
    firstPaint = false;
  };

  const wire = (open, variations, roll) => {
    const input = app.querySelector("#botfile");
    const drop = app.querySelector("[data-drop]");
    const button = app.querySelector("[data-upload]");
    const label = app.querySelector("[data-filename]");
    const verdict = app.querySelector("[data-verdict]");
    if (!input) return;

    // Everything below is re-checked on the server; catching it here just saves
    // the reader a round trip and a sandbox run to be told about a typo.
    const problemWith = (file) => {
      const match = FILENAME_RE.exec(file.name);
      if (!match) return `“${file.name}” is not named ROLLNO_<variation>.py`;
      if (roll && match[1].toUpperCase() !== roll.toUpperCase()) {
        return `That file is named for ${match[1].toUpperCase()}, but you are signed in as ${roll}.`;
      }
      if (!variations.includes(Number(match[2]))) {
        return `Variation ${match[2]} is not in play. Currently accepted: ${variations
          .map((id) => `V${id}`)
          .join(", ")}.`;
      }
      return "";
    };

    const showChosen = () => {
      const file = input.files?.[0];
      label.textContent = file ? file.name : "Drop your .py file here";
      label.classList.toggle("text-flame", Boolean(file));
      button.disabled = !file || busy || !open;
    };

    input.addEventListener("change", showChosen);

    ["dragenter", "dragover"].forEach((name) =>
      drop.addEventListener(name, (event) => {
        event.preventDefault();
        drop.classList.add("border-flame");
      })
    );
    ["dragleave", "drop"].forEach((name) =>
      drop.addEventListener(name, (event) => {
        event.preventDefault();
        drop.classList.remove("border-flame");
      })
    );
    drop.addEventListener("drop", (event) => {
      const file = event.dataTransfer?.files?.[0];
      if (!file) return;
      const transfer = new DataTransfer();
      transfer.items.add(file);
      input.files = transfer.files;
      showChosen();
    });

    button.addEventListener("click", async () => {
      const file = input.files?.[0];
      if (!file || busy) return;

      const problem = problemWith(file);
      if (problem) {
        result = { ok: false, message: problem };
        verdict.innerHTML = verdictCard(result);
        toast(problem, "error", 7000);
        return;
      }

      busy = true;
      button.disabled = true;
      button.textContent = "Running the sandbox…";
      verdict.innerHTML = "";

      try {
        result = await api.submit(file);
        toast("Accepted, your bot is in the next showdown.", "ok");
        const me = await api.me();
        store.set({ me });
        paint();
      } catch (error) {
        result = { ok: false, message: error.message };
        toast(error.message, "error", 8000);
        verdict.innerHTML = verdictCard(result);
      } finally {
        busy = false;
        button.disabled = false;
        button.textContent = "Run the checks and submit";
      }
    });
  };

  paint();

  // Repaint when the organisers open or close submissions, or release another
  // variation, so the page never invites an upload it will refuse.
  let signature = JSON.stringify([store.state?.variations, store.state?.submissions_open]);
  const unsubscribe = store.subscribe(() => {
    const next = JSON.stringify([store.state?.variations, store.state?.submissions_open]);
    if (next === signature || busy) return;
    signature = next;
    paint();
  });

  return unsubscribe;
}
