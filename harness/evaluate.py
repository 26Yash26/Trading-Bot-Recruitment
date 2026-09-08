"""The showdown: every submitted bot, every enabled variation, ranked.

This is what the 2-hourly scheduler calls, and the same code path the final
evaluation on 24 Sep uses — only the settings differ. Following the problem
statement §8: split into random groups, play a full game per group, repeat with
fresh seeds and fresh groups, then aggregate.

Groups are independent games, so they run in parallel across processes. The
wall-clock cost is roughly::

    variations x repeats x ceil(n/group_size) x len(capitals) x ~15 s / workers
"""

from __future__ import annotations

import math
import random
import statistics
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path

from sandbox.runner import SandboxLimits

from .simulate import BotOutcome, BotSpec, make_groups, play_group


@dataclass
class ShowdownSettings:
    """Everything the admin page can turn. Defaults follow the problem statement."""

    variations: tuple[int, ...] = (1, 2, 3)
    num_rounds: int = 2000
    group_size: int = 20
    repeats: int = 3
    starting_capitals: tuple[float, ...] = (100.0,)
    max_bid: float = 100.0
    block_bounds: tuple[tuple[float, float], ...] = (
        (0.0, 100.0), (0.0, 100.0), (0.0, 100.0), (0.0, 100.0),
    )
    seed: int = 20260923
    workers: int = 4
    round_timeout: float = 1.0
    mem_mb: int = 512

    def limits(self) -> SandboxLimits:
        return SandboxLimits(round_timeout=self.round_timeout, mem_mb=self.mem_mb)


@dataclass
class LeaderboardRow:
    key: str
    variation: int
    games: int = 0
    mean_net_profit: float = 0.0
    std_net_profit: float = 0.0
    best_net_profit: float = 0.0
    worst_net_profit: float = 0.0
    mean_final_capital: float = 0.0
    wins: int = 0
    survival_rate: float = 1.0
    errors: int = 0
    timeouts: int = 0
    disqualified: bool = False
    reason: str = ""
    rank: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class ShowdownResult:
    started_at: float
    finished_at: float
    games_played: int
    rows: list[LeaderboardRow] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return self.finished_at - self.started_at


def _play_one(job: dict) -> list[dict]:
    """Worker entry point — must be module-level and picklable."""
    specs = [BotSpec(key=k, path=Path(p)) for k, p in job["specs"]]
    result = play_group(
        specs,
        variation=job["variation"],
        starting_capitals=job["capital"],
        block_bounds=job["block_bounds"],
        seed=job["seed"],
        max_bid=job["max_bid"],
        num_rounds=job["num_rounds"],
        limits=SandboxLimits(round_timeout=job["round_timeout"], mem_mb=job["mem_mb"]),
        tier=job.get("tier"),
    )
    return [asdict(o) for o in result.outcomes if not o.is_filler]


def build_jobs(submissions: dict[int, list[BotSpec]], settings: ShowdownSettings) -> list[dict]:
    """One job per (variation, repeat, group, starting capital)."""
    jobs: list[dict] = []
    for variation in settings.variations:
        specs = submissions.get(variation) or []
        if not specs:
            continue
        for repeat in range(settings.repeats):
            rng = random.Random(settings.seed + variation * 1000 + repeat)
            for group_idx, group in enumerate(make_groups(specs, settings.group_size, rng)):
                if not group:
                    continue
                for cap_idx, capital in enumerate(settings.starting_capitals):
                    jobs.append(
                        {
                            "specs": [(s.key, str(s.path)) for s in group],
                            "variation": variation,
                            "capital": capital,
                            "block_bounds": [tuple(b) for b in settings.block_bounds],
                            "seed": settings.seed + repeat * 97 + group_idx * 13 + cap_idx,
                            "max_bid": settings.max_bid,
                            "num_rounds": settings.num_rounds,
                            "round_timeout": settings.round_timeout,
                            "mem_mb": settings.mem_mb,
                        }
                    )
    return jobs


def aggregate(outcomes: list[BotOutcome]) -> list[LeaderboardRow]:
    """Collapse every game a bot played into one ranked row per variation."""
    buckets: dict[tuple[str, int], list[BotOutcome]] = {}
    for outcome in outcomes:
        buckets.setdefault((outcome.key, outcome.variation), []).append(outcome)

    rows: list[LeaderboardRow] = []
    for (key, variation), group in buckets.items():
        profits = [o.net_profit for o in group]
        survived = sum(1 for o in group if o.eliminated_round is None)
        dq = [o for o in group if o.disqualified]
        rows.append(
            LeaderboardRow(
                key=key,
                variation=variation,
                games=len(group),
                mean_net_profit=statistics.fmean(profits),
                std_net_profit=statistics.pstdev(profits) if len(profits) > 1 else 0.0,
                best_net_profit=max(profits),
                worst_net_profit=min(profits),
                mean_final_capital=statistics.fmean([o.final_capital for o in group]),
                wins=sum(o.wins for o in group),
                survival_rate=survived / len(group),
                errors=sum(o.errors for o in group),
                timeouts=sum(o.timeouts for o in group),
                disqualified=bool(dq),
                reason=dq[0].reason if dq else "",
            )
        )

    # Rank within each variation. A disqualified bot always sorts last.
    for variation in {r.variation for r in rows}:
        subset = sorted(
            [r for r in rows if r.variation == variation],
            key=lambda r: (r.disqualified, -r.mean_net_profit),
        )
        for position, row in enumerate(subset, start=1):
            row.rank = position
    return rows


def run_showdown(
    submissions: dict[int, list[BotSpec]],
    settings: ShowdownSettings,
    *,
    progress=None,
) -> ShowdownResult:
    """Play every game and return the ranked leaderboard.

    ``progress(done, total)`` is called after each finished game, so the admin
    page can show a live bar.
    """
    started = time.time()
    jobs = build_jobs(submissions, settings)
    outcomes: list[BotOutcome] = []
    errors: list[str] = []

    if not jobs:
        return ShowdownResult(started, time.time(), 0, [], [])

    workers = max(1, min(settings.workers, len(jobs)))
    done = 0

    if workers == 1:
        for job in jobs:
            try:
                outcomes.extend(BotOutcome(**d) for d in _play_one(job))
            except Exception as exc:  # noqa: BLE001 - one bad group must not stop the rest
                errors.append(f"variation {job['variation']}: {exc}"[:300])
            done += 1
            if progress:
                progress(done, len(jobs))
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_play_one, job): job for job in jobs}
            for future in as_completed(futures):
                job = futures[future]
                try:
                    outcomes.extend(BotOutcome(**d) for d in future.result())
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"variation {job['variation']}: {exc}"[:300])
                done += 1
                if progress:
                    progress(done, len(jobs))

    rows = aggregate(outcomes)
    return ShowdownResult(started, time.time(), len(jobs), rows, errors)


def estimate_seconds(n_bots: int, settings: ShowdownSettings, per_game: float = 15.0) -> float:
    """Rough wall-clock estimate, used to warn the admin before they hit Run."""
    groups = max(1, math.ceil(n_bots / max(1, settings.group_size)))
    games = (
        len(settings.variations)
        * settings.repeats
        * groups
        * max(1, len(settings.starting_capitals))
    )
    scaled = per_game * (settings.num_rounds / 2000)
    return games * scaled / max(1, settings.workers)
