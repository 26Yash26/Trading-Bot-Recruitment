# Context

Quick orientation for anyone (or any agent) picking this repo up cold.
Deeper detail lives in `docs/`; this is the map.

## What it is

The website and infrastructure for the **Quant Guild Trading Bot competition**,
IIT Madras, odd semester 2026. Participants write a Python bot that plays a
repeated sealed-bid auction. The site takes the submission, checks it in a
sandbox on upload, replays the whole field on a schedule, and publishes a
leaderboard.

Live at <https://quantguildiitm.in>.

## The game, in one screen

Source of truth: `Quant_Guild_Application_updated.pdf` (kept in the parent
folder, not in the repo). The engine implements it exactly.
`docs/scoring.tex` is the normative write-up of the scoring and the tournament,
written against the code.

- **20 bots per group, 2000 rounds, split into 4 blocks of 500.**
- Each round every solvent bot privately draws `xᵢ ~ U[m_b, M_b]`. Both bounds
  are hidden and change every block. Nobody is told when a block boundary
  happens. Detecting it is part of the problem.
- **The bounds are drawn, not chosen.** Per block, independently:
  `m_b ~ {10, 20, … 1000}` (step 10) and `range_b ~ {100, 200, … 10000}`
  (step 100), with `M_b = m_b + range_b`. 10,000 possible blocks, spanning two
  orders of magnitude in both the floor and the width. The minimum is never
  zero, and width is independent of scale. The **grids are published**; the seed
  is not, and every iteration draws its own schedule, so nothing is learnable
  across showdowns. `bounds_mode = "fixed"` takes a hand-typed schedule instead,
  for reproducing a specific run (and for the engine tests).
- **Your legal bid ceiling is your own capital.** Over it, negative, NaN or late
  is filed as a bid of 0.
- **Capital is redrawn at every block boundary**: `κ ~ U[0.5, 2.5]`,
  `capital = m_b + range_b · κ`. Anchored to the block's floor, scaled by its
  *width*, so κ always means "how many block-widths of headroom I start with".
  Since `m_b ≥ 10` and `range_b ≥ 100` the smallest draw is 60, which is why the
  formula needs no floor term and no jitter. What you finished the previous
  block with does not carry over. Bankruptcy costs you the rest of *that block*
  only.
- **Four variations** (3 and 4 are released only after mock auction 1):
  1. Private value, first price. The winner takes `xᵢ − b₁`.
  2. Common value, first price. The winner takes `X − b₁`, where X is the
     maximum value over the active players.
  3. Runner-up penalty. The winner takes `X − b₁`; rank 2 pays `−0.5(X − b₁)`.
  4. Funded second price. Rank 1 takes `X − b₂` and rank 2 takes `X − b₁`, funded
     0.5/0.3/0.2 by ranks 3 to 5. Zero-sum. If `b₁ > X` the winner alone eats it.
  V1/V2 let every tied top bidder win; V3/V4 break ties uniformly at random.
- **Scoring is normalised, not raw profit.** Per block,
  `π = (C_end − C_start) / M_b`; standardised within the group to
  `P = 50 + 15·clip(z, ±3)`. Iteration score = sum of 4 blocks; total = sum over
  iterations. The board ranks on score.

## The tournament, and what a run is

A **showdown** is the whole tournament, played end to end. By default that is
five iterations:

| Iteration | Grouping | What it does |
|---|---|---|
| 1, 2 | `random` | the field shuffled into groups of 20 on a fresh seed |
| 3 | `balanced` | sorted by points so far and dealt in a snake, so groups are equal in average strength |
| 4, 5 | `finals` | only the leading `finals_size` bots, head to head |

Iterations play in order, because a balanced or finals iteration seeds on the
standing after the ones before it. They cannot all be planned up front.

`grouping` is a list with one mode per iteration and `iterations` is its length;
the admin page edits them as one control, so the two can never disagree. A list
shorter than `iterations` holds its last entry.

A showdown can also be run for **one variation at a time**. The live board takes
each variation from the newest run that scored it, so replaying variation 1
leaves variation 2 exactly as it was.

**There is no live board.** The site shows the mock rounds and the finals, and
nothing in between. Nothing runs on a timer: `showdown_enabled` is off, and a
showdown is started from the admin page as an announced event.

Every showdown is stamped with a **kind**, and it is not a label:

| | `practice` | `mock` | `final` |
|---|---|---|---|
| What it is | a private rehearsal | an announced round | the run after the deadline |
| Public? | never | published and kept | published and kept |
| Seeds a balanced run from | the last rehearsal | the last mock | the last final |

Published boards are listed in the leaderboard's *Boards* picker and reachable
at `/api/leaderboard?showdown=<id>`. A practice run is invisible to
participants: not on the board, not in the archive, not in `/api/state`. It
exists so the pipeline can be proved before an announced round.

Any showdown can be deleted from Admin, History. Deleting the newest mock makes
the one before it current again, both on the site and as the standing the next
mock seeds on. A running showdown cannot be deleted.

## Layout

| Path | What |
|---|---|
| `index.html`, `web/` | the site: a hand-written SPA, ES modules, no build step but Tailwind |
| `web/js/pages/` | one module per route: home, leaderboard, rules, submit, login, admin |
| `web/js/motion.js` | scroll reveals, counters, parallax, cursor ring |
| `web/src/input.css` | the design system; build with `./scripts/build_css.sh` |
| `server/` | FastAPI: API, Google OAuth, scheduler, SQLite store |
| `server/late_variations.js` | the V3/V4 browser copy: served by the API, 404 until released |
| `src/auction/` | the engine: round loop, variations, bounds grids, capital, scoring |
| `harness/` | upload validation, grouped simulation, leaderboard aggregation |
| `sandbox/` | AST policy, per-bot child process, isolation tiers |
| `starter-kit/` | what participants download now (`build_kit.py` builds the zip) |
| `late-kit/` | V3/V4 templates + runner, staged until mock auction 1 |
| `docs/scoring.tex` | the scoring spec; `build_docs.sh` makes both PDFs |
| `deploy/` | nginx config, systemd units, env template |
| `tests/` | 267 tests |

## Running it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m scripts.seed_demo    # optional fake field
python -m server               # http://localhost:8000
pytest
```

Google OAuth is not configured locally. `seed_demo` prints an admin session
cookie; see `docs/RUNBOOK.md` for how to use it.

Editing the frontend: `./scripts/build_css.sh --watch`, and **commit
`web/css/app.css`**, because the VM has no build step. `tests/test_web_assets.py`
structurally checks every served module, since nothing else would catch a
syntax slip before it blanked the site.

Try a bot against the real engine: `python run_local.py --bot x.py --variation 4`.

## Two things that must be rebuilt and committed

The VM has no build step, so these artefacts live in git:

```bash
python build_kit.py          # -> public/starter-kit.zip
./scripts/build_docs.sh      # -> docs/scoring{,-public}.pdf
```

Tests fail if either is stale. `build_kit.py --release-v3-v4` builds the other
kit. See the release procedure in `docs/RUNBOOK.md`.

## The admin page

`/admin`, gated on `QG_ADMIN_EMAILS`. It is the only place the competition's
shape changes, and it covers everything: which variations are released, cadence,
rounds and block size, group size, tournament iterations and per-iteration
grouping, the capital draw, whether bounds are drawn or fixed, the seed, sandbox
limits, bans, the announcement banner, the deadline, and the submission form
link. Showdowns are started from there as practice, mock or final.

Settings live in the SQLite `settings` table, not in code. A change is pushed to
every open browser over the leaderboard SSE stream, so releasing a variation
takes effect everywhere without a reload.

New columns reach the VM's database through `store.MIGRATIONS`. It holds every
real submission and is never dropped and recreated, so `CREATE TABLE IF NOT
EXISTS` is a no-op there.

## Embargo: variations 3 and 4

There are two things a participant can get hold of before release: the kit zip
and whatever the browser is served. `tests/test_embargo.py` checks both, plus the
scoring PDFs. Nothing about V3/V4 sits in the JS bundle or in `starter-kit/`;
the copy lives in `server/late_variations.js` and `late-kit/`, neither of which
nginx will serve. `docs/scoring.tex` compiles twice so the public PDF can go out
now without describing them.

## Deploying

**Anything on `main` is live.** Every push to `main` runs a GitHub Action that
SSHes into the GCP VM and hard-resets `/var/www/html` to `origin/main`; a systemd
path unit restarts the API. Feature branches do not deploy. Do not modify
`.github/`.

`/var/www/html` is a checkout of this whole private repo, so what is reachable
over HTTP is decided by an allowlist in `deploy/nginx.conf`, not by convention.
See `docs/SECURITY.md` §1.
