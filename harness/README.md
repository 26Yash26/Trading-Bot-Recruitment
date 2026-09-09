# harness/

Organiser-only evaluation code. **Not for participants**, and not reachable from
the deployed web root (`deploy/nginx.conf` serves an allowlist, see
`docs/SECURITY.md` §1).

| File | Job |
|---|---|
| `simulate.py` | one sandboxed group game; grouping and filler bots |
| `validate.py` | accept or reject a single submission |
| `evaluate.py` | a whole showdown: iterations × groups, aggregated and ranked |

## How it fits together

`server/scheduler.py` calls `evaluate.run_showdown` every `interval_minutes`.
It plays the run's iterations **in order**, one job per (variation, group)
within each, fanning the groups of one iteration across a process pool, then
aggregates every game a bot played into one ranked row per variation.

Iterations are sequential rather than all-at-once because `grouping` is set per
iteration (§9: `["random", "random", "balanced", "finals", "finals"]`), and a
`balanced` or `finals` iteration snake-seeds or cuts on the standing *after* the
iterations before it. `build_jobs` still returns the whole plan up front, which
is what sizing and tests want, but it is not what runs.

A run also carries a **kind**, `practice`, `mock` or `final`, recorded on the
`showdowns` row. It decides whether the board is archived and published, and
which previous board a balanced or finals run is seeded from
(`Scheduler.current_seeding` reads the last finished run of the same kind).

`validate.validate` runs on upload instead: filename and roll check, then the
static policy (`sandbox/policy.py`), then a 120-round game against the sample
bots. A participant gets the verdict in a few seconds.

Both paths reach the engine through `sandbox.runner.SandboxedBotFactory`, which
the engine treats as an ordinary bot class, see `docs/ARCHITECTURE.md`.

## Running one by hand

```python
from harness.evaluate import ShowdownSettings, run_showdown
from harness.simulate import BotSpec

field = {1: [BotSpec(key="ME24B152", path="/var/lib/quantguild/submissions/ME24B152_1.py")]}
result = run_showdown(field, ShowdownSettings(iterations=1, num_rounds=500))

for row in sorted(result.rows, key=lambda r: r.rank):
    print(row.rank, row.key, round(row.mean_net_profit, 2))
```
