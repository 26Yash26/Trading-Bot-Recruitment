# Trading Bot Competition — Build Checklist

Working doc for the 3 organisers building the competition infra. Tick items off in PRs
(`- [x]`), one PR per sub-section where possible.

- **Repo:** `github.com/26Yash26/Trading-Bot-Recruitment` (this repo — **PUBLIC**, auto-deploys to the GCP VM)
- **Deadline for participants:** 23 Sep 2026, 23:59
- **PS launch:** 09 Sep 2026 (Wed) — Phase 0 must be done before this
- **Mock auction:** ~20 Sep 2026 (2–3 days before deadline)
- **Today:** 08 Sep 2026 → ~2 weeks of runway, Phase 0 is ~1 day

---

## 0. Ground rules (read once)

### 0.1 What is this repo
This repo is the **public server** for the recruitment. `.github/workflows/deploy.yml`
SSHes into the GCP VM on every push to `main` and runs `git reset --hard origin/main`
inside `/var/www/html`. So:

- **Anything merged to `main` is live and publicly downloadable within seconds.**
- **Do not touch `.github/` or `.github/workflows/`** (README says so — if CI genuinely
  needs changing, get sign-off from the repo owner / Yash first).
- Never commit hidden competition parameters here (distribution bounds, starting
  capitals used for grading, the grading sample-bot gauntlet). Those live in the
  **separate private repo** (see 0.2).

### 0.2 Two repos
| Repo | Visibility | Holds |
|---|---|---|
| `Trading-Bot-Recruitment` (this one) | public | landing page, PS/rules, **starter kit**, reference simulator, sample bots |
| `trading-bot-eval` (to create — **private**) | private | evaluation harness, grading, secret run config, mock-auction runner, results |

The reference simulator in the public repo and the engine used by the private harness
should be **the same code** — put the engine in the public repo (participants are told
they may read it) and have the private harness import/vendor it.

### 0.3 Git workflow
- `main` = deployed. **No direct commits, ever.**
- Branch naming: `feat/<area>`, `fix/<area>`, `docs/<area>`, `chore/<area>`.
- 1 PR → 1 review from another dev → **squash merge**.
- Tag after each phase with an annotated tag: `git tag -a v0.1.0 -m "Engine core"` then
  `git push origin v0.1.0`. Versions:
  - `v0.1.x` — engine
  - `v0.2.x` — starter kit / website (Phase 0 ships as `v0.2.0`… keep numbering by
    completion order, not phase number; adjust when we tag)
  - `v0.3.x` — harness (private repo has its own tags)
  - `v1.0.0` — everything green, competition live
- **Rollback:** `git revert <sha>` on `main` (auto-redeploys the previous state). Only
  `git reset --hard <tag> && git push --force origin main` in an emergency, and announce
  it first — it force-deploys.
- Before merging anything that changes a deployed file (`index.html`, `public/…`), open
  the built site locally and eyeball it.

### 0.4 Owners
| Dev | Area |
|---|---|
| **Dev A** | `src/auction/` core engine + the bot interface contract + engine tests |
| **Dev B** | sandbox/runtime wrapper, submission validation, **private** eval harness, integration tests |
| **Dev C** | starter kit (Template, sample bots, participant README), website, build/zip pipeline, docs |

---

## Phase 0 — Launch-critical (before 09 Sep)

Goal: participants can read the PS and download a starter kit that runs.

### 0.A Repo scaffold  — _Dev C_  — branch `chore/scaffold`
- [ ] Add `.gitignore` (`venv/`, `__pycache__/`, `*.pyc`, `*.log`, `logs/`, `.env`, `*.zip` except built kit, `.DS_Store`, `.idea/`, `.vscode/`)
- [ ] Add `requirements.txt` (pin: `numpy`, `pandas`, `matplotlib`; dev: `pytest`, `psutil`)
- [ ] Add `README.md` for **devs** (what this repo is, the two-repo split, how to run tests) — keep the existing "don't touch `.github`" note
- [ ] Create the folder skeleton (see "Target layout" at the bottom) with `__init__.py` and short `README.md` stubs
- [ ] Tag `v0.0.1` once merged

### 0.B Bot interface contract  — _Dev A_  — branch `feat/bot-interface`  — **BLOCKS EVERYTHING**
- [ ] Write `docs/bot_interface.md` — the frozen contract participants code against
- [ ] Decide the shape of "highest & 2nd-highest bids of previous 100 rounds": **scalars**
      (max over the window) vs **per-round lists** (len ≤ 100). _Proposal: give both —
      `hist_highest`/`hist_second` scalars for simple bots, `hist_highest_series`/
      `hist_second_series` lists for the rest._
- [ ] Freeze the `Template.py` API. **Proposed:**
  ```python
  class Bot:
      def __init__(self, bot_id, starting_capital, max_bid, num_players):
          ...
      def get_bid(self, obs) -> float:
          # obs = {
          #   'x': float,                # your private value this round
          #   'round': int,              # 0-based
          #   'capital': float,          # your capital right now
          #   'num_players': int,        # players active THIS round
          #   'max_bid': float,          # legal bid ceiling
          #   'hist_highest': float|None,        # over last <=100 rounds
          #   'hist_second': float|None,
          #   'hist_highest_series': list[float], # per-round, oldest->newest
          #   'hist_second_series': list[float],
          # }
          return 0.0
  ```
- [ ] Confirm nothing conflicting was already circulated on the guild WhatsApp
- [ ] Confirm `max_bid` value with organisers ("specified ahead of the competition")
- [ ] Same interface serves all 3 variations (participant tunes strategy per variation,
      submits `<Rollno>_1.py` / `_2.py` / `_3.py`)

### 0.C Reference simulator — minimum viable  — _Dev A_  — branch `feat/engine-core`
Enough for participants to self-test. Full polish continues in Phase 1.
- [ ] `src/auction/config.py` — `NUM_ROUNDS=2000`, `BLOCK_SIZE=500`, `HISTORY_WINDOW=100`
- [ ] `src/auction/distributions.py` — blocked uniform; 4 blocks of 500; bounds passed in
      (never hard-coded), reproducible via seed
- [ ] `src/auction/variations.py` — `payoff_v1`, `payoff_v2`, `payoff_v3`; V3 second-bidder
      rule with the `X - bid < 0 → 0` clamp
- [ ] `src/auction/history.py` — rolling 100-round window of (highest, second) bids
- [ ] `src/auction/engine.py` — round loop: draw values → collect bids → legality
      (`bid>capital → 0`, clamp to `[0, max_bid]`) → winner(s) = max bid, ties all win →
      payoff → capital update → eliminate at capital `<= 0` → record history
- [ ] `src/auction/player.py` — thin wrapper around a bot instance (no sandbox yet)
- [ ] **Test against the PDF sample run** (`tests/test_variations.py`): 3 bots, x = 30/50/60,
      bids 45/55/30, cap 100 each →
      V1 winner −5 (→95); V2 winner +5 (→105); V3 winner +5, 2nd −2.5 (→97.5)
- [ ] `run_local.py` at repo root — `python run_local.py --bot my_bot.py --variation 1`
      runs your bot vs the 3 sample bots, prints capital-over-time + net profit

### 0.D Starter kit  — _Dev C_  — branch `feat/starter-kit`
- [ ] `starter-kit/Template.py` — the frozen API from 0.B, with a trivial default
      (e.g. `bid = 0.5 * x`) and heavy comments
- [ ] `starter-kit/sample_bots/` — 3 bots from the PDF sample run:
      `bid = x + 15`, `bid = x + 5`, `bid = 0.5 * x` (clamp to `[0, max_bid]`, respect capital)
- [ ] `starter-kit/auction_reference/` — read-only copy (or symlink at build time) of
      `src/auction/` so participants can see how it's simulated
- [ ] `starter-kit/README.md` — participant-facing: install, how to fill in `Template.py`,
      how to run `run_local.py`, the 3 variations, submission naming
      (`<Rollno>_1.py` etc.), limits (1 s/round, <100 MB, any library but list it in report,
      no network), link back to the PS PDF
- [ ] `build_kit.py` (or a Make target) → produces `public/starter-kit.zip`
- [ ] Decide: commit `starter-kit.zip` or build it in a release step. _Proposal: commit it
      (no build step on the VM), rebuild on every kit change._

### 0.E Website / landing page  — _Dev C_  — branch `feat/site-ps`
- [ ] Replace the "coming soon" `index.html` with the real page: title, short overview,
      timeline, **download PS PDF**, **download starter kit**, rules summary, WhatsApp link
- [ ] `public/Quant_Guild_Application.pdf` — the PS
- [ ] Keep it a single static file + `public/` assets (no build; server just serves files)
- [ ] Mobile-friendly, works with JS disabled
- [ ] Test locally (`python -m http.server` in repo root) before merging — **this deploys**
- [ ] Merge + tag `v0.2.0` = "Launch"

### 0.F Launch gate
- [ ] All Phase 0 PRs merged to `main`, deploy went green (check VM / site loads)
- [ ] Download the kit from the live site on a clean machine, run `run_local.py` — it works
- [ ] Post links in the guild group

---

## Phase 1 — Harden the engine (09–14 Sep)

### 1.A Runtime sandbox  — _Dev B_  — branch `feat/sandbox`
- [ ] Per-round **timeout** (~1 s) — kill/skip the bot's `get_bid`, treat as bid 0 (or last
      bid) on timeout. Use a subprocess or signal-based timeout; document the choice.
- [ ] **Memory cap** (~100 MB) — `resource.setrlimit` (Linux) / `psutil` monitor; over-limit
      bot is disqualified
- [ ] **No network / no filesystem escape** — block sockets, restrict `open`, no `subprocess`
- [ ] Catch every exception from participant code → bot bids 0 that round, log it; N crashes
      in a row → disqualify
- [ ] `__init__` also time-boxed
- [ ] `tests/test_sandbox.py` — bots that sleep, allocate 500 MB, `open('/etc/passwd')`,
      `import socket`, raise, return `NaN` / negative / `>max_bid` / a string

### 1.B Engine correctness & edge cases  — _Dev A_  — branch `feat/engine-hardening`
- [ ] Elimination semantics: exact rule for "runs out of capital" (`<= 0`? can't afford any
      positive bid?) — write it down, test it
- [ ] `num_players` each round reflects only non-eliminated bots
- [ ] All-players-eliminated / 1-player-left termination
- [ ] Tie handling: all tied top bidders win and each gets the full payoff (confirm vs
      organisers' intent), V3 "second-highest" when the top is a tie
- [ ] Negative payoffs allowed (capital can drop); illegal bid auto-set to 0 logged
- [ ] Determinism: full run reproducible from a single seed
- [ ] Float precision (use a small epsilon for tie comparison? decide & document)
- [ ] `tests/test_engine.py`, `tests/test_distributions.py`, `tests/test_history.py`

### 1.C Simulation output  — _Dev A + Dev C_  — branch `feat/sim-reporting`
- [ ] Per-run log: capital-over-time per bot, wins, total payoff, round of elimination
- [ ] `src/auction/report.py` — summary table + matplotlib plots (capital vs round)
- [ ] JSON/CSV dump of a run for later analysis
- [ ] Tag `v0.3.0`

---

## Phase 2 — Evaluation harness (private repo, 12–18 Sep)

Lives in **`trading-bot-eval` (private)**. Imports the engine from the public repo
(git submodule or vendored copy — decide in 2.A).

### 2.A Private repo setup  — _Dev B_
- [ ] Create private repo `trading-bot-eval`
- [ ] Pull in the engine (submodule pointing at a tag of this repo, or vendored + a sync script)
- [ ] `secret_config.py` (git-ignored / committed only to private repo): the 4 hidden
      `(min,max)` distribution bounds per 500-round block, the set of starting capitals to
      sweep, RNG master seed
- [ ] `README.md` — how to run a full evaluation

### 2.B Submission intake & validation  — _Dev B_  — branch `feat/validate`
- [ ] Filename check: `^[A-Z0-9]+_(1|2|3)\.py$`, roll-no format
- [ ] Import each submission in the sandbox; reject on import error
- [ ] Smoke test: run vs the 3 sample bots for a short game — must not crash, must not go
      broke immediately, must return legal bids
- [ ] Report per submission: pass / fail + reason
- [ ] Dedupe: latest file per (rollno, variation) wins

### 2.C Grouped simulation  — _Dev B_  — branch `feat/eval-run`
- [ ] Random split of all passing bots into groups of 20 (pad with our filler/sample bots
      if not divisible)
- [ ] Run each group for the full 2000 rounds, per variation
- [ ] **Repeat 3×** with fresh seeds + re-randomised groups; aggregate
- [ ] **Starting-capital sweep** (robustness metric) — run the whole thing at each capital
      in `secret_config`
- [ ] Parallelise across cores; guard total wall-clock

### 2.D Results & metrics  — _Dev B + Dev C_  — branch `feat/eval-report`
- [ ] Per bot: net profit (mean ± std across the 3 repeats), capital-over-time, #wins,
      survival, rank distribution, sensitivity to starting capital
- [ ] Per-participant report (net profit + capital variation plot) — the artefact shared
      after the mock auction
- [ ] Leaderboard CSV (internal)
- [ ] Tag `v0.1.0` in the private repo

---

## Phase 3 — Mock auction (~20 Sep)

- [ ] Announce date on the guild group (Dev C)
- [ ] Freeze a submission window; collect codes from the form
- [ ] Run 2.B → 2.C → 2.D on real submissions
- [ ] Send each participant their stats (net profit, capital-over-time plot)
- [ ] Triage: bots that crash / time out / hog memory → notify participants with the error
- [ ] File issues for any engine/sandbox bugs the real bots expose; fix before final

## Phase 4 — Final evaluation (24 Sep, after deadline)

- [ ] Pull final submissions
- [ ] Full run: validation → 3× grouped sim → capital sweep, all 3 variations
- [ ] Generate final leaderboard + per-participant reports
- [ ] Archive: tag `v1.0.0` (public) + `v1.0.0` (private) + zip of all submissions + results
- [ ] Shortlisting decision (report quality + adaptivity + robustness, per PS §9)

---

## Target repo layout (this public repo)

```
Trading-Bot-Recruitment/
├── .github/workflows/deploy.yml     # DO NOT TOUCH
├── index.html                       # landing page (DEPLOYED)
├── public/
│   ├── Quant_Guild_Application.pdf
│   └── starter-kit.zip              # built artefact
├── run_local.py                     # participant self-test entrypoint
├── build_kit.py                     # zips starter-kit/ -> public/starter-kit.zip
├── requirements.txt
├── .gitignore
├── README.md                        # dev-facing
├── src/
│   └── auction/
│       ├── __init__.py
│       ├── config.py
│       ├── distributions.py
│       ├── variations.py            # V1 / V2 / V3 payoffs
│       ├── history.py
│       ├── player.py
│       ├── engine.py
│       └── report.py
├── starter-kit/
│   ├── Template.py                  # the ONLY file participants edit
│   ├── README.md                    # participant-facing
│   ├── auction_reference/           # read-only copy of src/auction
│   └── sample_bots/
│       ├── sample_bot_1.py
│       ├── sample_bot_2.py
│       └── sample_bot_3.py
├── tests/
│   ├── test_engine.py
│   ├── test_variations.py
│   ├── test_distributions.py
│   ├── test_history.py
│   └── test_sandbox.py
└── docs/
    ├── BUILD_CHECKLIST.md            # this file
    ├── ARCHITECTURE.md
    └── bot_interface.md              # frozen participant contract
```

## Open decisions (resolve as they come up)
- [ ] Timeout mechanism: subprocess-per-bot (safe, slow) vs in-process signal (fast, leaky)
- [ ] Engine sharing public↔private: git submodule vs vendored copy + sync script
- [ ] `starter-kit.zip`: committed vs release-built
- [ ] "prev 100 rounds bids" = scalars vs per-round series (proposal: both)
- [ ] Exact elimination threshold for capital
- [ ] Tie payoff: full payoff to each winner vs split
