# Architecture

Four pieces that barely know about each other: an **engine** that plays one
auction, a **sandbox** that runs untrusted bots, a **harness** that turns
submissions into a leaderboard, and a **server** that puts it on the web.

```
                 browser (static SPA, no build step)
                          │  fetch /api/…  ·  EventSource /api/leaderboard/stream
                          ▼
   nginx ──/web/ /public/──▶ files on disk
     │
     └──/api/──▶ server/app.py ──┬── server/store.py      SQLite: users, sessions,
                                 │                        submissions, results, audit
                                 ├── server/scheduler.py  the 2-hourly clock
                                 └── server/events.py     SSE fan-out
                                            │
                                            ▼
                                 harness/evaluate.py      iterations × groups
                                            │             (ProcessPoolExecutor)
                                            ▼
                                 harness/simulate.py      one group, one game
                                            │
                       ┌────────────────────┴────────────────────┐
                       ▼                                         ▼
            src/auction/engine.py                       sandbox/runner.py
            (the round loop)                            one child process per bot
                                                                 │
                                                                 ▼
                                                        sandbox/child.py
                                                        rlimits · no stdout · no net
```

## The join that makes this cheap

The engine calls `bot_cls(config)` and then `.get_bid(obs)`. That is the *whole*
contract, so `sandbox.runner.SandboxedBotFactory`, a callable returning an
object with `get_bid`, drops into `run_game` with **no engine changes at all**.
Sandboxing is invisible to the auction logic, and `run_local.py` keeps working
with plain in-process classes.

The same property handles failures: a timeout, a crash or a killed process all
surface as an exception, and `auction.player.Player` already converts any
exception from a bot into a bid of `0` plus an error count.

## Components

| Module | Job |
|---|---|
| `src/auction/config.py` | fixed PS constants |
| `src/auction/distributions.py` | `ValueSampler`, blocked uniform, hidden bounds, seeded |
| `src/auction/variations.py` | V1 / V2 / V3 payoff rules |
| `src/auction/history.py` | rolling 100-round bid window |
| `src/auction/player.py` | bot wrapper: bid sanitising, capital, elimination |
| `src/auction/engine.py` | `run_game(...) -> GameResult` |
| `src/auction/loader.py` | load a `Bot` class from a path (used by `run_local.py`) |
| `sandbox/policy.py` | AST allowlist, applied at upload time |
| `sandbox/child.py` | the process a bot runs in |
| `sandbox/runner.py` | parent side: isolation tier, per-round timeout, disqualification |
| `harness/simulate.py` | one sandboxed group game, plus grouping and filler bots |
| `harness/validate.py` | accept/reject one submission |
| `harness/evaluate.py` | a whole showdown, parallel across groups, aggregated and ranked |
| `server/store.py` | SQLite |
| `server/scheduler.py` | the clock; persists `next_run_at` |
| `server/app.py` | API, OAuth, admin |
| `web/` | the frontend |

## Data flow

**One round** (`engine.run_game`): draw `x_i` for active players → build `obs`
per bot → collect and sanitise bids → highest bid wins, ties all win → payoffs
per variation → `capital += payoff` → eliminate at `capital <= 0` → record the
round's top two bids.

**One submission** (`POST /api/submit`): session and roll check → cooldown and
rate limit → size and UTF-8 check → filename parse → AST policy → 120-round
sandboxed game against the sample bots → accept (file written to
`QG_DATA_DIR/submissions`, previous file for that variation deactivated) or
reject with a reason.

**One showdown** (`scheduler.run_once`): stamp the run `practice`, `mock` or
`final` → collect the latest accepted file per `(roll, variation)`, minus banned
rolls → for each iteration **in order**, build one job per (variation, group)
using that iteration's grouping and the standing so far → run those jobs across a
process pool → aggregate per `(roll, variation)` into score, mean/worst/spread of
π, survival and raw profit → rank → write to `results` → publish over SSE.

The kind is not a label. `mock` and `final` boards are archived and stay
reachable (`GET /api/leaderboard?showdown=<id>`) after the two-hourly practice
clock has replaced the live one, and a balanced or finals run seeds only on the
last finished run **of its own kind**, otherwise its snake seeding is built from
whichever practice run happened to land most recently. `docs/scoring.tex` §7-8
is the normative description.

## The frontend has no build step

The VM serves files straight from the git checkout and has no node. So the site
is hand-written ES modules plus one Tailwind stylesheet built by Tailwind's
**standalone binary** (`scripts/build_css.sh`) and committed as
`web/css/app.css`. There is no bundler, no `node_modules`, and nothing to
install on the VM.

Routing is history-API based; every unknown path renders `index.html`, which is
also what keeps the document root safe (see `docs/SECURITY.md`).

## Deployment

GitHub Actions hard-resets `/var/www/html` to `origin/main`. That updates files
but restarts nothing, and `.github/` is off limits by repo policy, so the VM
watches for the deploy itself: `quantguild-deploy.path` triggers on
`.git/FETCH_HEAD` changing and restarts the API. See `docs/RUNBOOK.md`.

## Key decisions

Tracked in `docs/BUILD_CHECKLIST.md` ("Open decisions") and
`docs/bot_interface.md` (⚠️ markers). The security reasoning is in
`docs/SECURITY.md`.
