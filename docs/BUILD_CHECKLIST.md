# Trading Bot Competition — Build Checklist

Working doc for building the competition infra. Tick items off in PRs (`- [x]`).

- **Repo:** `github.com/26Yash26/Trading-Bot-Recruitment` (private, auto-deploys to the GCP VM on push to `main`)
- **Today:** 08 Sep 2026
- **PS launch:** 09 Sep 2026 (Wed)
- **Mock auction:** ~20 Sep 2026
- **Participant deadline:** 23 Sep 2026, 23:59
- **Final evaluation:** 24 Sep 2026

---

## Where things stand

The engine, sandbox, harness, website, live leaderboard and admin console are
built and tested (86 tests). What is left before launch is **operational**, not
code: point the VM at the new stack, set the real secrets, and confirm the
document root is not exposed. See "Launch gate" below.

---

## 0. Ground rules

### 0.1 What this repo is
Single private repo holding **everything** — landing page, PS, starter kit, the
auction engine, the evaluation harness, the web service and the deploy config.

`.github/workflows/deploy.yml` SSHes into the GCP VM on every push to `main` and
runs `git reset --hard origin/main` inside `/var/www/html`.

- **Do not touch `.github/` or `.github/workflows/`.** The workflow does not need
  to change: the VM restarts the API itself via `quantguild-deploy.path`, which
  triggers on `.git/FETCH_HEAD` changing.
- [x] **Web server config — RESOLVED.** The deployed web root is a checkout of
      this whole repo, so `deploy/nginx.conf` serves an **allowlist** only
      (`/api/`, `/web/`, `/public/`) and never resolves a request path against
      the filesystem. `secret/`, `server/`, `harness/`, `sandbox/` and `.git/`
      are unreachable by construction, not by convention.
      Asserted by `tests/test_server.py::test_no_request_path_becomes_a_file_path`.
- [x] **Secrets are not in the repo.** OAuth credentials and the admin list live
      in `/etc/quantguild.env` (mode 640, outside the web root); the hidden
      distribution bounds live in the SQLite settings table in
      `/var/lib/quantguild`, editable from the admin page.

### 0.2 Git workflow
- **All git / GitHub commands are run by Sid.** Nobody else pushes.
- **Commit identity:** commits are authored as `hedgestat`.
- `main` = deployed. **No direct commits to `main`.**
- One task = one branch: `git checkout -b feat/<area>` → work → merge `--no-ff`
  back to `main` → push (this deploys) → delete the branch.
- Annotated tags at each milestone.
  - `v0.1.x` engine · `v0.2.x` launch · `v0.3.x` sandbox + reporting
  - `v0.4.x` harness · `v0.5.x` website + live leaderboard · `v1.0.0` competition live
- **Rollback:** `git revert <sha>` on `main` (auto-redeploys, and the path unit
  restarts the API).
- Before merging anything that changes a deployed file, run `python -m server`
  and eyeball it.

### 0.3 CI / running the tests
- The only workflow is `deploy.yml`. **Nothing runs `pytest` automatically** —
  run it yourself before every merge. Adding a test workflow means editing
  `.github/`, which needs 26Yash26's sign-off.
- The sandbox is POSIX-only. On native Windows the bot-spawning tests in
  `tests/test_sandbox.py` skip themselves (~10 skips, 0 failures; the AST-policy
  tests still run). Run the full suite on Linux / macOS / WSL.
- [ ] Get sign-off to add a `pytest` workflow (`ubuntu-latest`, install
      `requirements.txt`, `apt install bubblewrap`, run `pytest`)   ← _Sid_

---

## Phase 0 — Launch-critical

### 0.A Repo scaffold
- [x] `.gitignore` (Python, venvs, editors, `secret/config.py`, `.local/`, run artifacts)
- [x] `requirements.txt` — engine, web service and dev dependencies
- [x] `pyproject.toml` + root `conftest.py` (also isolates the test data directory)
- [x] Dev-facing `README.md`
- [x] Folder skeleton
- [x] `src/auction/config.py` fully populated
- [x] `config.MAX_BID` set to `100.0` (was `None`, which made the engine unusable
      without an explicit caller). The live value is an admin setting.
      ← _confirm the final number with the organisers_
- [ ] Tag `v0.0.1` after merge   ← _Sid_

### 0.B Bot interface contract
- [x] `docs/bot_interface.md` written, now marked **FROZEN (shipped)**
- [x] `starter-kit/Template.py` + `starter-kit/README.md` match it
- [x] Same interface serves all 3 variations
- [x] API shape frozen by shipping the starter kit — `Bot(config)` / `get_bid(obs)`
- [ ] Confirm the ⚠️ *engine-behaviour* decisions (see "Open decisions") — these
      don't change the API, so they can be settled after launch
- [ ] Check nothing conflicting was circulated on the guild WhatsApp   ← _Sid_

### 0.C Reference simulator
- [x] `config.py`, `distributions.py`, `variations.py`, `history.py`
- [x] `engine.py` — `run_game(...) -> GameResult`
- [x] `player.py` — bid sanitising, capital, elimination
- [x] `loader.py`
- [x] **PDF sample run passes** — V1 →[100,95,100], V2 →[100,105,100], V3 →[97.5,105,100]
- [x] `run_local.py`
- [x] `starter-kit/sample_bots/sample_bot_{1,2,3}.py`

### 0.D Starter kit
- [x] `starter-kit/Template.py` — frozen API, trivial default, heavy comments
- [x] `starter-kit/sample_bots/` — the 3 PDF bots
- [x] `starter-kit/auction_reference/` — read-only copy, generated by `build_kit.py`
- [x] `starter-kit/README.md` — participant-facing
- [x] `build_kit.py` → `public/starter-kit.zip`, committed
- [x] Verified: a clean extract of the zip runs `run_local.py` successfully

### 0.E Website
- [x] Replaced the "coming soon" page — home, rules, leaderboard, submit, login, admin
- [x] Mobile-friendly; checked at 390 px and 1440 px
- [x] Tested locally before merging
- [ ] `public/Quant_Guild_Application.pdf` — the PS as a downloadable PDF.
      The rules page renders the full problem statement as HTML, so this is a
      convenience, not a blocker. ← _Sid, export from the LaTeX source_
- [ ] Merge + tag `v0.2.0`

### 0.F Launch gate
- [ ] Install **bubblewrap** on the VM (`sudo apt install bubblewrap`) — until
      then the sandbox falls back to a weaker tier and the admin page says so in red
- [ ] Create the `quantguild` service user, `/var/lib/quantguild`, `/opt/quantguild/venv`
- [ ] Fill in `/etc/quantguild.env` (OAuth client, `QG_ADMIN_EMAILS`, public origin)
- [ ] Register the Google OAuth redirect URI
- [ ] Install the systemd units and `deploy/nginx.conf`
- [ ] **Verify the document root is not exposed** — `curl .../secret/config.py`,
      `.../server/store.py` and `.../.git/config` must all return `<!DOCTYPE html>`
- [ ] certbot, then set `QG_PUBLIC_ORIGIN=https://…` so cookies get `Secure`
- [ ] Set the real hidden bounds and seed in the admin console
- [ ] Press **Run a showdown now** and confirm the leaderboard fills
- [ ] Download the kit from the live site on a clean machine and run it
- [ ] Post links in the guild group

All of Phase 0.F is in [`docs/RUNBOOK.md`](RUNBOOK.md) as copy-pasteable commands.

---

## Phase 1 — Harden the engine

### 1.A Runtime sandbox — **done**
- [x] Per-round **timeout** — the child process is killed; the round scores as a
      bid of 0 and the bot sits out the rest of that game.
      *Chosen: subprocess per bot.* A per-round timeout is only enforceable if
      the thing you kill is just that bot.
- [x] **Memory cap** — `RLIMIT_AS`, default 512 MB (see `docs/SECURITY.md` for
      why not the 100 MB the PS quotes), admin-tunable
- [x] **No network / no filesystem escape** — bubblewrap namespace, read-only
      `/usr`, no `/home`, no `/etc`, `RLIMIT_FSIZE=0`, `RLIMIT_NPROC=0`
- [x] Every exception from participant code → bid 0 + log; 25 in a row → disqualified
- [x] `__init__` time-boxed
- [x] Static AST allowlist at upload time (`sandbox/policy.py`)
- [x] Protocol integrity — a bot's `print` cannot forge a bid
- [x] `tests/test_sandbox.py` — sleeps, 2 GB allocations, `open('/etc/passwd')`,
      `import socket`, raises, `NaN`/negative/string returns, `__class__` escapes,
      `getattr` indirection, string-splitting bypasses

### 1.B Engine correctness & edge cases
- [x] `num_players` each round reflects only non-eliminated bots
- [x] All-eliminated / 1-player-left termination
- [x] Tie handling: all tied top bidders win, each gets the full payoff
- [x] Negative payoffs allowed; illegal bid auto-set to 0
- [x] Determinism: a full run is reproducible from one seed
- [x] Float precision — `TIE_EPSILON = 1e-9`, documented
- [ ] Elimination semantics: `<= 0` vs "cannot afford any positive bid" — still
      the team's call (engine implements `<= 0`)

### 1.C Simulation output
- [x] Per-run results: capital over time, wins, net profit, round of elimination
- [x] Aggregation: mean ± std, best/worst, survival rate, rank
- [ ] `src/auction/report.py` — matplotlib capital-vs-round plots and a CSV/JSON
      dump. **Still a stub.** Needed for the per-participant artefacts sent after
      the mock auction (Phase 3), not for the website.
- [ ] Tag `v0.3.0`

---

## Phase 2 — Evaluation harness — **done**

### 2.A Secret config
- [x] Hidden `(min, max)` bounds per block, starting capitals and master seed —
      stored in the database, editable from the admin console, filtered out of
      every public API response
- [x] `secret/config.example.py` retained as the offline template

### 2.B Submission intake & validation
- [x] Filename check `^ROLLNO_(1|2|3)\.py$` + roll-number format
- [x] Roll bound to the signed-in smail address — you cannot submit as someone else
- [x] Static policy check; reject with a line number
- [x] Smoke test against the 3 sample bots — no crash, no timeout, not instantly broke
- [x] Per-submission verdict shown to the participant immediately
- [x] Dedupe: latest accepted file per (roll, variation) wins

### 2.C Grouped simulation
- [x] Random split into groups of 20, padded with sample bots when short
- [x] Full run per group, per variation
- [x] Repeats with fresh seeds and re-randomised groups
- [x] Starting-capital sweep
- [x] Parallel across cores; admin page estimates wall-clock and warns at >70% of the interval

### 2.D Results & metrics
- [x] Per bot: mean ± std net profit, best/worst, mean final capital, wins,
      survival rate, errors/timeouts, rank
- [x] Live public leaderboard with per-variation tabs
- [ ] Per-participant report (net profit + capital-over-time plot) — needs 1.C
- [ ] Internal leaderboard CSV export
- [ ] Tag `v0.4.0`

---

## Phase 3 — Website & live competition — **done**

- [x] Public leaderboard, updated over server-sent events
- [x] Countdown to the next showdown, clock-skew corrected against the server
- [x] Google OAuth restricted to `@smail.iitm.ac.in`; `state`-protected;
      `HttpOnly` session cookies
- [x] Submit page: drag-and-drop, immediate sandbox verdict, submission history
- [x] Rules page — the full problem statement, no PDF needed
- [x] **Admin console** — interval, variations, rounds, group size, repeats,
      workers, max bid, starting capitals, hidden bounds, seed, timeouts, memory
      ceiling, submissions open/closed, bans, announcements, run-now, audit log
- [x] Rate limiting, per-roll cooldown, upload size cap, CSP, XSS escaping
- [x] `deploy/` — nginx allowlist, systemd units, deploy-triggered restart
- [ ] Tag `v0.5.0`

---

## Phase 4 — Mock auction (~20 Sep)
- [ ] Announce the date on the guild group
- [ ] Back up `/var/lib/quantguild` before the run
- [ ] Send each participant their stats (needs 1.C for the plots)
- [ ] Triage bots that crash / time out / hog memory → notify participants
- [ ] File issues for anything the real bots expose; fix before final

## Phase 5 — Final evaluation (24 Sep)
- [ ] Close submissions from the admin page
- [ ] Full run: 3× grouped sim × capital sweep, all 3 variations, 2000 rounds
- [ ] Final leaderboard + per-participant reports
- [ ] **Read the top submissions by hand** before shortlisting — the policy check
      is not a substitute for reading code
- [ ] Archive: tag `v1.0.0` + a zip of all submissions and results
- [ ] Shortlisting (report quality + adaptivity + robustness, per PS §9)

---

## Open decisions

- [ ] Exact elimination threshold for capital (engine: `capital <= 0`)
- [ ] **Zero-bid free-win**: whole field bids 0 → everyone "wins" and pockets
      `x_i` for nothing. Keep (bidding is then a real undercut race) / no winner
      at bid 0 / minimum bid? (engine currently: keep — `docs/bot_interface.md` rule 6)
- [ ] "prev 100 rounds bids" = scalars vs per-round series (engine: both)
- [ ] Tie payoff: full payoff to each winner vs split (engine: full to each)
- [ ] V3 "second-highest bidder" when the top bid is a tie (engine: bidders at
      the highest bid *strictly below* the winning bid; none if there is no lower bid)
- [ ] Final `MAX_BID` to announce (engine default: `100.0`)
- [ ] Whether the public leaderboard shows real names or only roll numbers
      (currently: roll number, with the name underneath)

## Settled

- [x] Timeout mechanism — **subprocess per bot** (see 1.A)
- [x] Web server config — **allowlist in nginx** (see 0.1)
- [x] `starter-kit.zip` — **committed**, built by `build_kit.py`; the VM has no build step
- [x] `secret/config.py` — **superseded**: the real values live in the database,
      outside the web root, editable from the admin page without a deploy
