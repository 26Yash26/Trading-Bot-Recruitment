# Trading Bot Competition — Build Checklist

Working doc for building the competition infra. Tick items off in PRs (`- [x]`).

- **Repo:** `github.com/26Yash26/Trading-Bot-Recruitment` (private, auto-deploys to the GCP VM on push to `main`)
- **Today:** 08 Sep 2026
- **PS launch:** 09 Sep 2026 (Wed) — Phase 0 must land before this
- **Mock auction:** ~20 Sep 2026
- **Participant deadline:** 23 Sep 2026, 23:59
- **Final evaluation:** 24 Sep 2026

---

## 0. Ground rules

### 0.1 What this repo is
Single private repo holding **everything** — landing page, PS, starter kit, the auction
engine, the evaluation harness, and the secret competition config. The GitHub repo is
private so committing secrets (distribution bounds, grading capitals, sample-bot gauntlet)
here is fine.

`.github/workflows/deploy.yml` SSHes into the GCP VM on every push to `main` and runs
`git reset --hard origin/main` inside `/var/www/html`.

- **Do not touch `.github/` or `.github/workflows/`** (README says so — sign-off from the
  repo owner first if CI genuinely needs a change).
- The deployed **web root is served by a plain file server**, so even though GitHub is
  private, `http://<vm>/<path>` will hand out any file that lands in `/var/www/html`.
  Keep `secret/` (bounds, grading config) and `harness/` out of what the server exposes:
  either the server is configured to only serve `index.html` + `public/`, or we
  `.gitignore` those paths from deploy / keep them in a sibling dir on the VM. **Confirm
  the web-server config before Phase 2.**

### 0.2 Git workflow
- **All git / GitHub commands are run by Sid.** Nobody else pushes or touches the remote.
- **Commit identity:** commits are authored as `hedgestat`. One-time, in this repo:
  ```
  git config user.name  "hedgestat"
  git config user.email "<hedgestat email>"
  ```
- `main` = deployed. **No direct commits to `main`.**
- One task = one branch. Flow:
  ```
  git checkout main && git pull
  git checkout -b feat/<area>        # branch off main
  # ...do the work, commit in small steps...
  git add -A && git commit -m "..."
  git checkout main && git pull
  git merge --no-ff feat/<area>      # merge back to main
  git push origin main               # this triggers the deploy
  git branch -d feat/<area>
  ```
  Branch prefixes: `feat/`, `fix/`, `docs/`, `chore/`.
- Annotated tags at each milestone: `git tag -a v0.1.0 -m "..." && git push origin v0.1.0`
  - `v0.1.x` engine · `v0.2.x` launch (starter kit + site) · `v0.3.x` sandbox + reporting
  - `v0.4.x` harness · `v1.0.0` competition live
- **Rollback:** `git revert <sha>` on `main` (auto-redeploys the previous state).
  `git reset --hard <tag> && git push --force origin main` only in an emergency, announced first.
- Before merging anything that changes a deployed file (`index.html`, `public/…`), serve
  the repo locally and eyeball it.

---

## Phase 0 — Launch-critical (before 09 Sep)

Goal: participants can read the PS and download a starter kit that runs.

### 0.A Repo scaffold — `chore/scaffold`
- [x] `.gitignore` (Python, venvs, editors, `secret/config.py`, run artifacts)
- [x] `requirements.txt` — `numpy`, `pandas`, `matplotlib`; dev: `pytest`, `psutil`
- [x] `pyproject.toml` + root `conftest.py` (so `import src.auction…` works under pytest)
- [x] Dev-facing `README.md` (path table, setup, test command, "don't touch `.github`" note)
- [x] Folder skeleton — `src/auction/`, `starter-kit/`, `harness/`, `secret/`, `tests/`,
      `public/`, `docs/`; every engine module is a stub with a docstring + signature that
      raises `NotImplementedError`; every test file collects as `skip`
- [x] `src/auction/config.py` fully populated (constants from the PS)
- [ ] Tag `v0.0.1` after merge   ← _Sid_
- [ ] Decide: keep `secret/config.py` git-ignored (current) vs version it   ← _team_

### 0.B Bot interface contract — `feat/bot-interface` — **BLOCKS EVERYTHING**
- [x] `docs/bot_interface.md` written (marked PROVISIONAL)
- [x] `starter-kit/Template.py` written to match it (class `Bot`, `__init__(config)`, `get_bid(obs)`)
- [ ] **Team sign-off on the contract** — in particular: ⚠️ scalars-only vs scalars+series
      for the 100-round bid history, and ⚠️ the exact elimination threshold. Scaffold
      assumes scalars+series and `capital <= 0`; both are documented and easy to flip.
- [ ] Check nothing conflicting was already circulated on the guild WhatsApp   ← _Sid_
- [ ] Confirm the `max_bid` value with organisers → set `config.MAX_BID`   ← _Sid_
- [x] Same interface serves all 3 variations (`variation` is in `config`; one file per variation)

### 0.C Reference simulator — minimum viable — `feat/engine-core`
- [x] `src/auction/config.py` — `NUM_ROUNDS=2000`, `BLOCK_SIZE=500`, `HISTORY_WINDOW=100` (done in 0.A)
- [x] `src/auction/distributions.py` — `ValueSampler` (blocked uniform, seed-reproducible, last block reused past 2000) + `FixedSampler` test helper
- [x] `src/auction/variations.py` — `payoff_v1/v2/v3_winner/v3_second`; V3 clamp at `X - bid < 0`
- [x] `src/auction/history.py` — rolling window; per-round series + max-over-window scalars
- [x] `src/auction/engine.py` — `run_game(...) -> GameResult`; round loop, ties-all-win, V3 second bidder, elimination, `capital_by_round`
- [x] `src/auction/player.py` — bot wrapper: builds config, sanitises bids (type/NaN/neg → 0, clamp to max_bid, `>capital` → 0), catches bot exceptions → 0, tracks capital/wins/elimination
- [x] `src/auction/loader.py` — load a `Bot` class from a .py path (shared by run_local + harness)
- [x] **PDF sample run passes** (`tests/test_variations.py`): V1 →[100,95,100], V2 →[100,105,100], V3 →[97.5,105,100]
- [x] `run_local.py` — `python run_local.py --bot my_bot.py --variation 1` vs the 3 sample bots; prints table + capital curve + your net profit
- [x] `starter-kit/sample_bots/sample_bot_{1,2,3}.py` created (needed by run_local; pulled forward from 0.D)
- [x] Tests: `test_variations` `test_engine` `test_distributions` `test_history` unskipped — **26 pass, 5 skip** (sandbox = 1.A)
- [ ] ⚠️ raise the **zero-bid free-win** behaviour with the team (see docs/bot_interface.md rule 6) — set `MAX_BID` / elimination rule after that call

### 0.D Starter kit — `feat/starter-kit`
- [ ] `starter-kit/Template.py` — frozen API from 0.B, trivial default (`bid = 0.5 * x`), heavy comments
- [ ] `starter-kit/sample_bots/` — the 3 PDF bots: `bid = x + 15`, `bid = x + 5`, `bid = 0.5 * x` (clamp to `[0, max_bid]`, respect capital)
- [ ] `starter-kit/auction_reference/` — read-only copy of `src/auction/` (generated by `build_kit.py`)
- [ ] `starter-kit/README.md` — participant-facing: install, filling in `Template.py`, running `run_local.py`, the 3 variations, submission naming, limits (1 s/round, <100 MB, any library but list it in the report, no network), link to the PS PDF
- [ ] `build_kit.py` → `public/starter-kit.zip`; commit the zip (no build step on the VM), rebuild on every kit change

### 0.E Website / landing page — `feat/site-ps`
- [ ] Replace the "coming soon" `index.html`: title, overview, timeline, **download PS PDF**, **download starter kit**, rules summary, WhatsApp link
- [ ] `public/Quant_Guild_Application.pdf`
- [ ] Single static file + `public/` assets, mobile-friendly, works with JS disabled
- [ ] Test locally (`python -m http.server`) before merging — **this deploys**
- [ ] Merge + tag `v0.2.0` = "Launch"

### 0.F Launch gate
- [ ] All Phase 0 PRs merged, deploy green, site loads on the VM
- [ ] Download the kit from the live site on a clean machine, run `run_local.py` — it works
- [ ] Post links in the guild group

---

## Phase 1 — Harden the engine (09–14 Sep)

### 1.A Runtime sandbox — `feat/sandbox`
- [ ] Per-round **timeout** (~1 s) — kill/skip `get_bid`, treat as bid 0 on timeout; subprocess vs signal-based, document the choice
- [ ] **Memory cap** (~100 MB) — `resource.setrlimit` / `psutil` monitor; over-limit → disqualify
- [ ] **No network / no filesystem escape** — block sockets, restrict `open`, no `subprocess`
- [ ] Catch every exception from participant code → bid 0 that round + log; N crashes in a row → disqualify
- [ ] `__init__` also time-boxed
- [ ] `tests/test_sandbox.py` — bots that sleep, allocate 500 MB, `open('/etc/passwd')`, `import socket`, raise, return `NaN` / negative / `>max_bid` / a string

### 1.B Engine correctness & edge cases — `feat/engine-hardening`
- [ ] Elimination semantics: exact rule for "runs out of capital" (`<= 0`? can't afford any positive bid?) — document + test
- [ ] `num_players` each round reflects only non-eliminated bots
- [ ] All-eliminated / 1-player-left termination
- [ ] Tie handling: all tied top bidders win, each gets full payoff (confirm intent); V3 "second-highest" when the top is tied
- [ ] Negative payoffs allowed; illegal bid auto-set to 0 is logged
- [ ] Determinism: full run reproducible from one seed
- [ ] Float precision — epsilon for tie comparison? decide + document
- [ ] `tests/test_engine.py`, `tests/test_distributions.py`, `tests/test_history.py`

### 1.C Simulation output — `feat/sim-reporting`
- [ ] Per-run log: capital-over-time per bot, wins, total payoff, round of elimination
- [ ] `src/auction/report.py` — summary table + matplotlib plots (capital vs round)
- [ ] JSON/CSV dump of a run
- [ ] Tag `v0.3.0`

---

## Phase 2 — Evaluation harness (12–18 Sep)

Lives in `harness/` + `secret/` in this repo. Confirm the web server does not expose these paths (0.1).

### 2.A Secret config — `feat/secret-config`
- [ ] `secret/config.py` — the 4 hidden `(min, max)` distribution bounds per 500-round block, the set of starting capitals to sweep, RNG master seed
- [ ] `secret/README.md` — what's in here, why it must not be shared / deployed

### 2.B Submission intake & validation — `feat/validate`
- [ ] Filename check `^[A-Z0-9]+_(1|2|3)\.py$` + roll-no format
- [ ] Import each submission in the sandbox; reject on import error
- [ ] Smoke test vs the 3 sample bots for a short game — no crash, not instantly broke, legal bids
- [ ] Per-submission report: pass / fail + reason
- [ ] Dedupe: latest file per (rollno, variation) wins

### 2.C Grouped simulation — `feat/eval-run`
- [ ] Random split of passing bots into groups of 20 (pad with filler/sample bots if not divisible)
- [ ] Full 2000-round run per group, per variation
- [ ] **Repeat 3×** with fresh seeds + re-randomised groups; aggregate
- [ ] **Starting-capital sweep** across the values in `secret/config.py`
- [ ] Parallelise across cores; guard total wall-clock

### 2.D Results & metrics — `feat/eval-report`
- [ ] Per bot: net profit (mean ± std across the 3 repeats), capital-over-time, #wins, survival, rank distribution, sensitivity to starting capital
- [ ] Per-participant report (net profit + capital-variation plot) — the artefact shared after the mock auction
- [ ] Internal leaderboard CSV
- [ ] Tag `v0.4.0`

---

## Phase 3 — Mock auction (~20 Sep)
- [ ] Announce the date on the guild group
- [ ] Freeze a submission window; collect codes from the form
- [ ] Run 2.B → 2.C → 2.D on real submissions
- [ ] Send each participant their stats (net profit, capital-over-time plot)
- [ ] Triage bots that crash / time out / hog memory → notify participants with the error
- [ ] File issues for engine/sandbox bugs the real bots expose; fix before final

## Phase 4 — Final evaluation (24 Sep)
- [ ] Pull final submissions
- [ ] Full run: validation → 3× grouped sim → capital sweep, all 3 variations
- [ ] Final leaderboard + per-participant reports
- [ ] Archive: tag `v1.0.0` + zip of all submissions + results
- [ ] Shortlisting (report quality + adaptivity + robustness, per PS §9)

---

## Target repo layout

```
Trading-Bot-Recruitment/
├── .github/workflows/deploy.yml     # DO NOT TOUCH
├── index.html                       # landing page (DEPLOYED)
├── public/
│   ├── Quant_Guild_Application.pdf
│   └── starter-kit.zip
├── run_local.py                     # participant self-test entrypoint
├── build_kit.py                     # builds starter-kit/ + zips to public/
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
│       ├── loader.py                # load a Bot class from a .py path
│       └── report.py
├── starter-kit/
│   ├── Template.py                  # the ONLY file participants edit
│   ├── README.md                    # participant-facing
│   ├── auction_reference/           # generated read-only copy of src/auction
│   └── sample_bots/
│       ├── sample_bot_1.py
│       ├── sample_bot_2.py
│       └── sample_bot_3.py
├── harness/                         # NOT deployed / not web-exposed
│   ├── validate.py
│   ├── run_group.py
│   ├── evaluate.py
│   └── report.py
├── secret/                          # NOT deployed / not web-exposed
│   ├── config.py                    # hidden bounds, grading capitals, seed
│   └── README.md
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

## Open decisions
- [ ] Web server config — does it serve the whole repo or just `index.html` + `public/`? (gates how `harness/` + `secret/` are protected)
- [ ] Timeout mechanism: subprocess-per-bot (safe, slow) vs in-process signal (fast, leaky)
- [ ] "prev 100 rounds bids" = scalars vs per-round series (proposal: both)
- [ ] Exact elimination threshold for capital (engine: `capital <= 0`)
- [ ] Tie payoff: full payoff to each winner vs split (engine: full to each)
- [ ] **Zero-bid free-win**: whole field bids 0 → everyone "wins" and pockets `x_i`
      for nothing. Keep (bidding = undercut race) / no winner at bid 0 / min bid?
      (engine currently: keep — see `docs/bot_interface.md` rule 6)
- [ ] V3 "second-highest bidder" when the top bid is a tie (engine: bidders at the
      highest bid *strictly below* the winning bid; none if there is no lower bid)
- [ ] `starter-kit.zip` committed vs release-built
