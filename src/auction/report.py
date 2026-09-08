"""Turn a GameResult (or several) into human-readable output.

Phase 1.C: summary table + matplotlib plots (capital vs round per bot), plus a
JSON/CSV dump for later analysis. Kept separate from the engine so the engine has
no plotting dependency on a hot path.

To implement (1.C):
    summarise(result) -> str
    plot_capital(result, path) -> None
    dump(result, path) -> None
"""

from __future__ import annotations


def summarise(result):
    raise NotImplementedError("1.C")
