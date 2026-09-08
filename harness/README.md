# harness/

Organiser-only evaluation code. **Not for participants**, and not reachable from
the deployed web root (`deploy/nginx.conf` serves an allowlist — see
`docs/SECURITY.md` §1).

| File | Job |
|---|---|
| `simulate.py` | one sandboxed group game; grouping and filler bots |
| `validate.py` | accept or reject a single submission |
| `evaluate.py` | a whole showdown: groups × repeats × capitals, aggregated and ranked |

## How it fits together

`server/scheduler.py` calls `evaluate.run_showdown` every `interval_minutes`.
That builds one job per (variation, repeat, group, starting capital), runs them
across a process pool, and aggregates every game a bot played into one ranked
row per variation.

`validate.validate` runs on upload instead: filename and roll check, then the
static policy (`sandbox/policy.py`), then a 120-round game against the sample
bots. A participant gets the verdict in a few seconds.

Both paths reach the engine through `sandbox.runner.SandboxedBotFactory`, which
the engine treats as an ordinary bot class — see `docs/ARCHITECTURE.md`.

## Running one by hand

```python
from harness.evaluate import ShowdownSettings, run_showdown
from harness.simulate import BotSpec

field = {1: [BotSpec(key="ME24B152", path="/var/lib/quantguild/submissions/ME24B152_1.py")]}
result = run_showdown(field, ShowdownSettings(repeats=1, num_rounds=500))

for row in sorted(result.rows, key=lambda r: r.rank):
    print(row.rank, row.key, round(row.mean_net_profit, 2))
```
