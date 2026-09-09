"""The showdown: every submitted bot, every enabled variation, ranked.

This is what the 2-hourly scheduler calls, and the same code path the final
evaluation on 16 Sep uses — only the settings differ. Following the problem
statement §8: split into random groups, play a full game per group, repeat with
fresh seeds and fresh groups, then aggregate.

Groups are independent games, so they run in parallel across processes. The
wall-clock cost is roughly::

    variations x iterations x ceil(n/group_size) x ~15 s / workers
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
from src.auction.capital import CapitalDraw
from src.auction.distributions import normalise_block_bounds

from .simulate import BotOutcome, BotSpec, make_groups, play_group


@dataclass
class ShowdownSettings:
    """Everything the admin page can turn. Defaults follow the problem statement.

    ``grouping`` picks which part of §9 this run reproduces:
    ``"random"`` is iterations 1 and 2, ``"balanced"`` is the snake-seeded
    iteration 3, and ``"finals"`` restricts the field to the leading
    ``finals_size`` bots and plays them head to head.
    """

    variations: tuple[int, ...] = (1, 2)
    num_rounds: int = 2000
    block_size: int = 500
    group_size: int = 20
    iterations: int = 3
    grouping: str = "random"
    finals_size: int = 20
    capital: CapitalDraw = field(default_factory=CapitalDraw)
    block_bounds: tuple = (
        # Four blocks that are genuinely different in scale AND in width. If all
        # four matched, there would be no regime to detect and the whole point of
        # the block structure would be switched off.
        (0.0, 100.0), (40.0, 60.0), (0.0, 400.0), (5.0, 25.0),
    )
    """Hidden value bounds. Either one schedule of blocks, reused by every
    iteration, or one schedule per iteration — see ``bounds_for_iteration``."""
    seed: int = 20260916
    workers: int = 4
    round_timeout: float = 1.0
    mem_mb: int = 512

    @property
    def num_blocks(self) -> int:
        return max(1, math.ceil(self.num_rounds / max(1, self.block_size)))

    def bounds_for_iteration(self, iteration: int) -> list[tuple[float, float]]:
        """The block schedule iteration ``iteration`` (0-based) plays.

        Problem statement §9 wants iteration 2 to be a genuinely fresh draw —
        "different value distributions", not the same ones under a new seed. So
        the admin may supply one schedule per iteration. Supplying a single
        schedule keeps the old behaviour, and a short list cycles, so three
        schedules across five iterations is a legal thing to ask for.
        """
        schedules = normalise_block_bounds(self.block_bounds)
        return schedules[iteration % len(schedules)]

    def limits(self) -> SandboxLimits:
        return SandboxLimits(round_timeout=self.round_timeout, mem_mb=self.mem_mb)


@dataclass
class LeaderboardRow:
    """One bot's standing in one variation.

    ``score`` is the ranking quantity: the sum of its iteration scores, each of
    which is the sum of that iteration's four standardised block scores. The
    figures reported alongside it are the ones the problem statement §8 asks for
    — absolute profitability, survival, worst block, and consistency.
    """

    key: str
    variation: int
    games: int = 0
    blocks: int = 0
    score: float = 0.0
    mean_block_points: float = 0.0
    mean_normalised_profit: float = 0.0
    worst_normalised_profit: float = 0.0
    normalised_profit_spread: float = 0.0
    survival_rate: float = 1.0
    mean_net_profit: float = 0.0
    std_net_profit: float = 0.0
    best_net_profit: float = 0.0
    worst_net_profit: float = 0.0
    mean_final_capital: float = 0.0
    wins: int = 0
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
        block_bounds=job["block_bounds"],
        seed=job["seed"],
        num_rounds=job["num_rounds"],
        block_size=job["block_size"],
        group_size=job["group_size"],
        capital_draw=CapitalDraw(**job["capital"]),
        limits=SandboxLimits(round_timeout=job["round_timeout"], mem_mb=job["mem_mb"]),
        tier=job.get("tier"),
    )
    return [asdict(o) for o in result.outcomes if not o.is_filler]


def build_jobs(
    submissions: dict[int, list[BotSpec]],
    settings: ShowdownSettings,
    *,
    seeding: dict[int, dict[str, float]] | None = None,
) -> list[dict]:
    """One job per (variation, iteration, group).

    ``seeding`` maps a variation to each bot's cumulative score so far. It is
    what iteration 3 balances groups with, and what the finals cut the field on.
    """
    jobs: list[dict] = []
    for variation in settings.variations:
        specs = submissions.get(variation) or []
        if not specs:
            continue

        points = (seeding or {}).get(variation) or {}
        if settings.grouping == "finals" and points:
            specs = sorted(specs, key=lambda s: -points.get(s.key, 0.0))[: settings.finals_size]
        group_seeding = points if settings.grouping in ("balanced", "finals") else None

        for iteration in range(settings.iterations):
            rng = random.Random(settings.seed + variation * 1000 + iteration)
            groups = make_groups(specs, settings.group_size, rng, seeding=group_seeding)
            for group_idx, group in enumerate(groups):
                if not group:
                    continue
                jobs.append(
                    {
                        "specs": [(s.key, str(s.path)) for s in group],
                        "variation": variation,
                        "block_bounds": settings.bounds_for_iteration(iteration),
                        "seed": settings.seed + iteration * 97 + group_idx * 13 + variation,
                        "num_rounds": settings.num_rounds,
                        "block_size": settings.block_size,
                        "group_size": settings.group_size,
                        "capital": settings.capital.as_dict(),
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
        points = [p for o in group for p in o.block_points]
        pis = [p for o in group for p in o.block_profits]
        blocks = sum(o.blocks_played for o in group)
        survived = sum(o.blocks_survived for o in group)
        dq = [o for o in group if o.disqualified]
        rows.append(
            LeaderboardRow(
                key=key,
                variation=variation,
                games=len(group),
                blocks=blocks,
                score=sum(o.iteration_score for o in group),
                mean_block_points=statistics.fmean(points) if points else 0.0,
                mean_normalised_profit=statistics.fmean(pis) if pis else 0.0,
                worst_normalised_profit=min(pis) if pis else 0.0,
                normalised_profit_spread=statistics.pstdev(pis) if len(pis) > 1 else 0.0,
                survival_rate=(survived / blocks) if blocks else 1.0,
                mean_net_profit=statistics.fmean(profits),
                std_net_profit=statistics.pstdev(profits) if len(profits) > 1 else 0.0,
                best_net_profit=max(profits),
                worst_net_profit=min(profits),
                mean_final_capital=statistics.fmean([o.final_capital for o in group]),
                wins=sum(o.wins for o in group),
                errors=sum(o.errors for o in group),
                timeouts=sum(o.timeouts for o in group),
                disqualified=bool(dq),
                reason=dq[0].reason if dq else "",
            )
        )

    # Rank within each variation on total score. A bot that played fewer
    # iterations than the rest would score lower purely for that, so the mean
    # block score breaks ties. A disqualified bot always sorts last.
    for variation in {r.variation for r in rows}:
        subset = sorted(
            [r for r in rows if r.variation == variation],
            key=lambda r: (r.disqualified, -r.score, -r.mean_block_points),
        )
        for position, row in enumerate(subset, start=1):
            row.rank = position
    return rows


def run_showdown(
    submissions: dict[int, list[BotSpec]],
    settings: ShowdownSettings,
    *,
    progress=None,
    seeding: dict[int, dict[str, float]] | None = None,
) -> ShowdownResult:
    """Play every game and return the ranked leaderboard.

    ``progress(done, total)`` is called after each finished game, so the admin
    page can show a live bar.
    """
    started = time.time()
    jobs = build_jobs(submissions, settings, seeding=seeding)
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
    games = len(settings.variations) * settings.iterations * groups
    scaled = per_game * (settings.num_rounds / 2000)
    return games * scaled / max(1, settings.workers)
