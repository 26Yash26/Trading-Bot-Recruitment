"""Template for `secret/config.py` (the real file is git-ignored).

Copy to `config.py` and fill in real values before running the evaluation.
"""

# Hidden uniform bounds (lo, hi) for x_i, one pair per 500-round block.
# NUM_BLOCKS == 4 for a 2000-round game.
BLOCK_BOUNDS = [
    (0.0, 100.0),   # rounds    0- 499
    (0.0, 100.0),   # rounds  500- 999
    (0.0, 100.0),   # rounds 1000-1499
    (0.0, 100.0),   # rounds 1500-1999
]

# Starting capitals to sweep for the robustness metric (PS §9).
STARTING_CAPITALS = [100.0, 250.0, 1000.0]

# Master RNG seed. Per-run seeds are derived from this so runs are reproducible.
MASTER_SEED = 20260923
