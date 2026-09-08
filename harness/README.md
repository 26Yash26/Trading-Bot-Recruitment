# harness/

Organiser-only evaluation code. **Not for participants** and it should not be
reachable from the deployed web root (see `docs/BUILD_CHECKLIST.md` §0.1).

Planned modules (Phase 2):

| File | Job |
|---|---|
| `validate.py`   | filename + roll-no check, import in sandbox, smoke game vs sample bots |
| `run_group.py`  | one group of 20, one variation, one seed |
| `evaluate.py`   | random grouping, all variations, `EVAL_REPEATS` repeats, starting-capital sweep |
| `report.py`     | per-bot + per-participant stats and plots, internal leaderboard CSV |

Reads hidden parameters from `secret/config.py`.
