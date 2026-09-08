# Trading-Bot-Recruitment

Infrastructure for the Quant Guild Trading Bot competition — odd semester 2026.

> **Note:** Do not modify `.github/` or the workflows folder. It is used to set up CI/CD.
> On every push to `main`, the deploy workflow SSHes into the GCP VM and hard-resets
> `/var/www/html` to `origin/main` — so **anything on `main` is live**.

## What's here

| Path | Purpose | Deployed? |
|---|---|---|
| `index.html`, `public/` | Public landing page + downloads (PS PDF, starter kit) | yes |
| `src/auction/` | The auction engine (round loop, distributions, payoff variations) | yes (participants may read it) |
| `starter-kit/` | What participants download — `Template.py`, sample bots, participant README | yes |
| `run_local.py` | Participant self-test: your bot vs the sample bots | yes |
| `harness/` | Evaluation harness (validation, grouped sims, reports) | yes, but not web-exposed |
| `secret/` | Hidden competition config — distribution bounds, grading capitals, seed | **`config.py` is git-ignored** |
| `tests/` | Test suite | yes |
| `docs/` | `BUILD_CHECKLIST.md`, `ARCHITECTURE.md`, `bot_interface.md` | yes |

## Setup

```
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux
pip install -r requirements.txt
```

## Run the tests

```
pytest
```

## Working on this repo

See [`docs/BUILD_CHECKLIST.md`](docs/BUILD_CHECKLIST.md) for the task list and the git
workflow. Short version: branch off `main`, do the work, merge back to `main`. Sid runs
all git/GitHub commands.
