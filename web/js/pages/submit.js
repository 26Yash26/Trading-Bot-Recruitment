// Upload a bot. Auth-gated, drag-and-drop, with the sandbox's verdict shown inline.

import { api } from "../api.js";
import { navigate, store } from "../main.js";
import { VARIATION_META, esc, relativeTime, signed, toast } from "../ui.js";

function historyList(submissions) {
  if (!submissions?.length) {
    return `<p class="px-5 py-8 text-center font-mono text-sm text-ink-faint">Nothing submitted yet.</p>`;
  }

  return submissions
    .map((row) => {
      const accepted = row.status === "accepted";
      const meta = VARIATION_META[row.variation];
      return `
        <div class="flex items-start gap-3 border-b border-line/60 px-5 py-3.5 last:border-b-0">
          <span class="mt-1 h-2 w-2 shrink-0 rounded-full ${accepted ? "bg-gain" : "bg-loss"}"></span>
          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-2">
              <span class="font-mono text-sm text-ink">${esc(row.filename)}</span>
              <span class="chip ${meta?.ring || ""} ${meta?.accent || ""} py-0.5">V${esc(row.variation)}</span>
              ${row.active ? `<span class="chip border-gain/40 py-0.5 text-gain">In play</span>` : ""}
            </div>
            ${
              row.message
                ? `<p class="mt-1 text-xs leading-relaxed text-loss">${esc(row.message)}</p>`
                : `<p class="mt-1 font-mono text-xs text-ink-faint">
                     smoke test net profit ${signed(row.smoke_profit)}
                   </p>`
            }
          </div>
          <span class="shrink-0 font-mono text-[11px] text-ink-faint">${esc(relativeTime(row.created_at))}</span>
        </div>`;
    })
    .join("");
}

function verdictCard(result) {
  if (!result) return "";

  if (!result.ok) {
    return `
      <div class="mt-6 animate-rise rounded-xl border border-loss/40 bg-loss/10 p-5">
        <p class="font-heading text-sm font-bold text-loss">Rejected</p>
        <p class="mt-1.5 text-sm leading-relaxed text-ink">${esc(result.message)}</p>
        <p class="mt-3 text-xs text-ink-dim">Fix it and upload again — there is no penalty for retrying.</p>
      </div>`;
  }

  const { smoke } = result;
  return `
    <div class="mt-6 animate-rise rounded-xl border border-gain/40 bg-gain/10 p-5">
      <p class="font-heading text-sm font-bold text-gain">Accepted</p>
      <p class="mt-1.5 text-sm text-ink">
        ${esc(result.roll)} · variation ${esc(result.variation)} is in the next showdown.
      </p>
      <dl class="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        ${[
          ["Smoke net profit", signed(smoke.net_profit)],
          ["Rounds won", smoke.wins],
          ["Errors", smoke.errors],
          ["Timeouts", smoke.timeouts],
        ]
          .map(
            ([label, value]) => `
          <div>
            <dt class="font-mono text-[10px] uppercase tracking-[0.16em] text-ink-faint">${label}</dt>
            <dd class="mt-0.5 font-mono text-sm text-ink">${esc(value)}</dd>
          </div>`
          )
          .join("")}
      </dl>
      <p class="mt-4 text-xs leading-relaxed text-ink-dim">
        That was a short game against the three sample bots, on stand-in bounds — a sanity check,
        not a ranking. The real distribution is hidden.
      </p>
    </div>`;
}

export async function renderSubmit(app) {
  if (!store.me.signed_in) {
    navigate("/login", { replace: true });
    return;
  }

  const open = store.state?.submissions_open !== false;
  const roll = store.me.roll || "";
  let result = null;
  let busy = false;

  const paint = () => {
    app.innerHTML = `
      <section class="mx-auto max-w-4xl px-5 py-14">
        <span class="chip border-gold/40 text-gold">Signed in as ${esc(store.me.email)}</span>
        <h1 class="mt-4 font-heading text-4xl font-bold md:text-5xl">Submit your bot</h1>
        <p class="mt-3 max-w-2xl text-sm leading-relaxed text-ink-dim">
          One file per variation, named
          <code class="font-mono text-gold">${esc(roll || "ROLLNO")}_&lt;variation&gt;.py</code>.
          It is checked the moment you upload it — static policy first, then a short game against
          the sample bots — and you get the verdict here.
        </p>

        ${
          open
            ? ""
            : `<div class="mt-6 rounded-xl border border-loss/40 bg-loss/10 px-4 py-3 text-sm text-loss">
                 Submissions are currently closed.
               </div>`
        }

        <div class="mt-8 grid gap-6 lg:grid-cols-[1.1fr_1fr]">
          <div>
            <label for="botfile"
                   class="group grid cursor-pointer place-items-center rounded-2xl border-2 border-dashed
                          border-line-bright bg-surface/50 px-6 py-14 text-center transition-all
                          hover:border-gold/60 hover:bg-surface-2/50 ${open ? "" : "pointer-events-none opacity-40"}"
                   data-drop>
              <input id="botfile" type="file" accept=".py,text/x-python" class="sr-only" ${open ? "" : "disabled"}>
              <span class="grid h-12 w-12 place-items-center rounded-xl border border-line-bright
                           bg-void/60 text-xl text-gold transition-transform group-hover:scale-110">↑</span>
              <span class="mt-4 font-heading text-base font-bold text-ink" data-filename>
                Drop your .py file here
              </span>
              <span class="mt-1 text-xs text-ink-faint">or click to choose · max 512 KB</span>
            </label>

            <button class="btn-gold mt-5 w-full" data-upload ${open ? "" : "disabled"} disabled>
              Run the checks and submit
            </button>

            <div data-verdict>${verdictCard(result)}</div>
          </div>

          <div>
            <h2 class="font-heading text-lg font-bold">Your submissions</h2>
            <div class="panel mt-4 overflow-hidden">${historyList(store.me.submissions)}</div>

            <div class="panel mt-5 p-5">
              <h3 class="font-heading text-sm font-bold">What gets checked</h3>
              <ul class="mt-3 space-y-2 text-xs leading-relaxed text-ink-dim">
                <li>▸ Filename matches your roll number and a valid variation.</li>
                <li>▸ The file defines a class <code class="font-mono text-gold">Bot</code> with
                    <code class="font-mono text-gold">get_bid</code>.</li>
                <li>▸ No imports outside the numeric stack, no <code class="font-mono">eval</code>,
                    <code class="font-mono">open</code> or interpreter introspection.</li>
                <li>▸ A 120-round game against the sample bots: it must not crash, time out,
                    or go broke.</li>
              </ul>
            </div>
          </div>
        </div>
      </section>`;

    wire();
  };

  const wire = () => {
    const input = app.querySelector("#botfile");
    const drop = app.querySelector("[data-drop]");
    const button = app.querySelector("[data-upload]");
    const label = app.querySelector("[data-filename]");
    const verdict = app.querySelector("[data-verdict]");
    if (!input) return;

    const showChosen = () => {
      const file = input.files?.[0];
      label.textContent = file ? file.name : "Drop your .py file here";
      label.classList.toggle("text-gold", Boolean(file));
      button.disabled = !file || busy || !open;
    };

    input.addEventListener("change", showChosen);

    ["dragenter", "dragover"].forEach((name) =>
      drop.addEventListener(name, (event) => {
        event.preventDefault();
        drop.classList.add("border-gold/70", "bg-surface-2/60");
      })
    );
    ["dragleave", "drop"].forEach((name) =>
      drop.addEventListener(name, (event) => {
        event.preventDefault();
        drop.classList.remove("border-gold/70", "bg-surface-2/60");
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

      busy = true;
      button.disabled = true;
      button.textContent = "Running the sandbox…";
      verdict.innerHTML = "";

      try {
        result = await api.submit(file);
        toast("Accepted — your bot is in the next showdown.", "ok");
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
}
