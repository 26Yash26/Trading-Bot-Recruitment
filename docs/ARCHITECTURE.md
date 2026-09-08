# Architecture

> Stub — fill in as the engine takes shape (0.C / 1.B).

## Components

```
run_local.py ─┐                          participant self-test
              ├─> src/auction/engine.run_game ──> GameResult
harness/     ─┘        │
                       ├─ distributions.ValueSampler   draw x_i per round (secret bounds)
                       ├─ player.Player                bot wrapper: obs, get_bid, sandbox, capital
                       ├─ variations                   V1 / V2 / V3 payoff rules
                       └─ history.BidHistory           rolling 100-round bid window
                       report                          summaries + plots + dumps
```

## Data flow per round
draw values → build obs per active bot → collect + sanitise bids → pick winner(s)
→ compute payoffs → update capital → eliminate broke bots → record round highs.

## Key decisions
Tracked in `docs/bot_interface.md` (⚠️ markers) and `docs/BUILD_CHECKLIST.md`
("Open decisions").
