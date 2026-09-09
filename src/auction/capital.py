"""Starting capital, redrawn at every block boundary (problem statement §3.1).

For each player independently, at the start of block b::

    kappa ~ U[0.5, 2.5]
    C     = m_b + range_b * kappa        (range_b = M_b - m_b)

So capital is anchored to the block's *floor* and scaled by its *width*. Inside
one block some bots start on half the block's range and some on two and a half
times it; nobody is told anyone else's capital.

Why this shape rather than a multiple of M_b alone. The block bounds are drawn
on grids (``distributions.draw_block_bounds``) where m_b can be a large fraction
of M_b — m_b = 1000 with a range of 100 gives M_b = 1100, a block where every
value sits within 10% of every other. Scaling capital by M_b there would hand
every bot roughly the same bankroll relative to the spread of values, which is
the one thing the capital draw exists to vary. Scaling by the range keeps
kappa's meaning constant: it is always "how many block-widths can I afford".

It also removes two patches the old formula needed. m_b >= 10 and range >= 100,
so the smallest possible capital is 10 + 100*0.5 = 60 -- comfortably positive,
with no floor term, and no additive jitter to keep a small block off zero.

The bounds are parameters rather than constants because the admin console can
tune them between showdowns.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CapitalDraw:
    """How a block's starting capital is drawn. Defaults follow the PS."""

    kappa_lo: float = 0.5
    kappa_hi: float = 2.5

    def draw(self, rng, block_min: float, block_max: float) -> float:
        """One player's starting capital for a block spanning ``[min, max]``."""
        block_min = float(block_min)
        block_range = float(block_max) - block_min
        kappa = rng.uniform(self.kappa_lo, self.kappa_hi)
        return block_min + block_range * kappa

    def as_dict(self) -> dict:
        return {"kappa_lo": self.kappa_lo, "kappa_hi": self.kappa_hi}

    @classmethod
    def from_settings(cls, settings: dict | None) -> "CapitalDraw":
        settings = settings or {}
        base = cls()
        return cls(
            kappa_lo=float(settings.get("kappa_lo", base.kappa_lo)),
            kappa_hi=float(settings.get("kappa_hi", base.kappa_hi)),
        )
