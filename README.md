# Trading-Bot-Recruitment

Infrastructure for the Quant Guild Trading Bot competition — odd semester 2026.

**Live:** <https://quantguildiitm.in> — deployed on the GCP VM behind nginx + TLS,
`@smail.iitm.ac.in` Google sign-in, `bwrap` sandbox, showdown every two hours.

Participants submit a Python bot. It is checked in a sandbox on upload, then
every two hours the whole field replays a 2000-round sealed-bid auction and the
public leaderboard is rewritten.

> **Do not modify `.github/`.** On every push to `main` the deploy workflow SSHes
> into the GCP VM and hard-resets `/var/www/html` to `origin/main` — so
> **anything on `main` is live**. The VM restarts the API itself via a systemd
> path unit; the workflow does not need to change. See `docs/RUNBOOK.md`.

## Run it locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python -m scripts.seed_demo     # optional: 18 fake participants
python -m server                # http://localhost:8000
```

One command serves the API and the site. Full instructions, including how to
open the admin console without Google OAuth: [`docs/RUNBOOK.md`](docs/RUNBOOK.md).

## What's here

| Path | Purpose | Web-exposed? |
|---|---|---|
| `index.html`, `web/` | the site — hand-written SPA, no build step | **yes** |
| `public/` | downloads: `starter-kit.zip` | **yes** |
| `server/` | API, Google OAuth, showdown scheduler, SQLite | no — proxied at `/api` |
| `sandbox/` | AST policy, per-bot child process, isolation tiers | no |
| `harness/` | validation, grouped simulation, leaderboard aggregation | no |
| `src/auction/` | the engine — round loop, distributions, payoff variations | no |
| `starter-kit/` | what participants download | no (shipped in the zip) |
| `secret/` | hidden bounds template — the real config lives in the database | no |
| `scripts/` | `seed_demo.py`, `build_css.sh` | no |
| `deploy/` | nginx config, systemd units, env template | no |
| `tests/` | 86 tests | no |
| `docs/` | architecture, security model, runbook, checklist, bot contract | no |

"Web-exposed" is enforced by an allowlist in `deploy/nginx.conf`, not by
convention — `/var/www/html` is a checkout of this whole repo, so everything
else has to be unreachable by construction. See
[`docs/SECURITY.md`](docs/SECURITY.md) §1.

## The stack

- **Frontend** — ES modules and Tailwind v4, built by Tailwind's *standalone
  binary*. No node, no npm, no `node_modules`, nothing to install on the VM.
  Rebuild with `./scripts/build_css.sh` and commit `web/css/app.css`.
- **Backend** — FastAPI + SQLite. Sessions are `HttpOnly` cookies; the OAuth
  flow is `state`-protected and restricted to `@smail.iitm.ac.in`.
- **Sandbox** — one process per bot, per-round timeout enforced by killing it,
  `setrlimit` ceilings, and namespace isolation via bubblewrap (or Docker).

## Tests

```bash
pytest
```

`tests/test_sandbox.py` is the important one: it submits infinite loops, memory
bombs, socket openers, filesystem readers, protocol-forging `print`s and
`__class__` escapes, and asserts each is contained.

## Documentation

| Doc | What's in it |
|---|---|
| [`docs/RUNBOOK.md`](docs/RUNBOOK.md) | run locally; stand up the VM; day-to-day operations |
| [`docs/SECURITY.md`](docs/SECURITY.md) | threat model, the three sandbox layers, known gaps |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | how the four pieces fit together |
| [`docs/BUILD_CHECKLIST.md`](docs/BUILD_CHECKLIST.md) | task list, milestones, open decisions |
| [`docs/bot_interface.md`](docs/bot_interface.md) | the frozen participant contract |

## Working on this repo

Branch off `main`, do the work, merge back. `main` is deployed, so serve the
site locally and eyeball it before merging anything that touches `index.html`,
`web/` or `public/`.

Pushing to `main` triggers the deploy: GitHub Actions hard-resets
`/var/www/html` on the VM, and a systemd path unit restarts the API (bounded
stop, so a live leaderboard stream can't hang the restart). The VM's `nginx`
and `systemd` config are installed once by `deploy/setup_vm.sh` (re-runnable);
a plain push does not reinstall them, so changes under `deploy/` need that
script re-run on the VM to take effect. See [`docs/RUNBOOK.md`](docs/RUNBOOK.md).
