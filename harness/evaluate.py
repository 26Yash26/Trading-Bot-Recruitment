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
from src.auction.distributions import draw_block_bounds, normalise_block_bounds

from .simulate import BotOutcome, BotSpec, make_groups, play_group

#: The grouping modes §9 defines. ``random`` draws groups blind; ``balanced``
#: snake-seeds them on cumulative points; ``finals`` cuts the field to the
#: leading ``finals_size`` and plays those head to head.
GROUPINGS = ("random", "balanced", "finals")


@dataclass
class ShowdownSettings:
    """Everything the admin page can turn. Defaults follow the problem statement.

    ``grouping`` picks which part of §9 each iteration reproduces:
    ``"random"`` is iterations 1 and 2, ``"balanced"`` is the snake-seeded
    iteration 3, and ``"finals"`` restricts the field to the leading
    ``finals_size`` bots and plays them head to head.

    It may be a single mode applied to every iteration, or **one mode per
    iteration** — ``("random", "random", "balanced", "finals", "finals")`` plays
    the whole of §9 in one run, with each iteration seeded on the ones before it
    rather than on whatever board happened to be published last. See
    ``grouping_for_iteration``.
    """

    variations: tuple[int, ...] = (1, 2)
    num_rounds: int = 2000
    block_size: int = 500
    group_size: int = 20
    iterations: int = 3
    grouping: str | tuple[str, ...] = "random"
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
    bounds_mode: str = "random"
    """How each iteration's hidden bounds are chosen.

    ``"random"`` draws them off the published grids
    (``distributions.draw_block_bounds``) from ``seed`` — the normal case, and
    what makes a schedule impossible to carry from one showdown to the next.
    ``"fixed"`` uses ``block_bounds`` verbatim, for reproducing a specific run.
    """

    seed: int = 20260916
    workers: int = 4
    round_timeout: float = 1.0
    mem_mb: int = 512

    @property
    def num_blocks(self) -> int:
        return max(1, math.ceil(self.num_rounds / max(1, self.block_size)))

    def grouping_schedule(self) -> tuple[str, ...]:
        """``grouping`` as a tuple of modes, validated."""
        value = self.grouping
        schedule = (value,) if isinstance(value, str) else tuple(str(m) for m in value)
        if not schedule:
            raise ValueError("grouping must name at least one mode")
        unknown = [m for m in schedule if m not in GROUPINGS]
        if unknown:
            raise ValueError(
                f"unknown grouping {unknown[0]!r}; expected one of {', '.join(GROUPINGS)}"
            )
        return schedule

    def grouping_for_iteration(self, iteration: int) -> str:
        """The mode iteration ``iteration`` (0-based) plays.

        A schedule shorter than ``iterations`` **holds its last entry** rather
        than cycling, which is what the block schedule does. Cycling is right
        for value bounds — every schedule there is an equally valid fresh draw —
        and wrong here: ``("random", "balanced")`` over five iterations should
        mean one random iteration and then four balanced ones, not an
        alternation that keeps throwing the field back into a random draw after
        it has been seeded.
        """
        schedule = self.grouping_schedule()
        return schedule[min(int(iteration), len(schedule) - 1)]

    def bounds_for_iteration(self, iteration: int) -> list[tuple[float, float]]:
        """The block schedule iteration ``iteration`` (0-based) plays.

        Problem statement §9 wants iteration 2 to be a genuinely fresh draw —
        "different value distributions", not the same ones under a new seed.

        Under ``bounds_mode="random"`` that is automatic: every iteration draws
        its own blocks off the grids, seeded on ``seed`` and the iteration index,
        so the run is reproducible while no two iterations share a schedule and
        nothing carries between showdowns.

        Under ``"fixed"`` the admin supplies the schedule. One schedule is reused
        by every iteration; a list of schedules is used one per iteration, and a
        short list cycles, so three schedules across five iterations is a legal
        thing to ask for.

        Every group *within* one iteration gets the same bounds either way. They
        have to: the standardised scores of two groups are only comparable if
        both faced the same distribution, and a balanced or finals iteration
        seeds on exactly that comparison.
        """
        if self.bounds_mode == "random":
            return draw_block_bounds(
                random.Random(self.seed * 7919 + iteration), self.num_blocks
            )
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


def build_iteration_jobs(
    submissions: dict[int, list[BotSpec]],
    settings: ShowdownSettings,
    iteration: int,
    *,
    seeding: dict[int, dict[str, float]] | None = None,
) -> list[dict]:
    """One job per (variation, group) for a single iteration.

    ``seeding`` maps a variation to each bot's cumulative score *going into this
    iteration*. It is what a ``balanced`` iteration snake-seeds groups with, and
    what a ``finals`` iteration cuts the field on. A ``random`` iteration ignores
    it entirely.
    """
    grouping = settings.grouping_for_iteration(iteration)
    jobs: list[dict] = []

    for variation in settings.variations:
        specs = submissions.get(variation) or []
        if not specs:
            continue

        points = (seeding or {}).get(variation) or {}
        if grouping == "finals" and points:
            specs = sorted(specs, key=lambda s: -points.get(s.key, 0.0))[: settings.finals_size]
        group_seeding = points if grouping in ("balanced", "finals") else None

        rng = random.Random(settings.seed + variation * 1000 + iteration)
        groups = make_groups(specs, settings.group_size, rng, seeding=group_seeding)
        for group_idx, group in enumerate(groups):
            if not group:
                continue
            jobs.append(
                {
                    "specs": [(s.key, str(s.path)) for s in group],
                    "variation": variation,
                    "iteration": iteration,
                    "grouping": grouping,
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


def build_jobs(
    submissions: dict[int, list[BotSpec]],
    settings: ShowdownSettings,
    *,
    seeding: dict[int, dict[str, float]] | None = None,
) -> list[dict]:
    """Every job in the run, in iteration order.

    Every iteration sees the same ``seeding`` here, so this is the *plan* rather
    than what actually runs: ``run_showdown`` rebuilds each iteration's jobs from
    the standing after the previous one. Kept because sizing, previewing and
    testing all want the whole list without playing a single game.
    """
    return [
        job
        for iteration in range(settings.iterations)
        for job in build_iteration_jobs(submissions, settings, iteration, seeding=seeding)
    ]


def seeding_from(outcomes: list[BotOutcome]) -> dict[int, dict[str, float]]:
    """Cumulative score per bot per variation, for the next iteration to seed on.

    This is the same quantity ``aggregate`` reports as ``score`` — the sum of the
    iteration scores so far — just computed without the rest of the row.
    """
    seeding: dict[int, dict[str, float]] = {}
    for outcome in outcomes:
        board = seeding.setdefault(outcome.variation, {})
        board[outcome.key] = board.get(outcome.key, 0.0) + outcome.iteration_score
    return seeding


def merge_seeding(*boards: dict[int, dict[str, float]] | None) -> dict[int, dict[str, float]]:
    """Add cumulative-score boards together, later ones on top of earlier ones."""
    merged: dict[int, dict[str, float]] = {}
    for board in boards:
        for variation, points in (board or {}).items():
            target = merged.setdefault(variation, {})
            for key, value in points.items():
                target[key] = target.get(key, 0.0) + float(value)
    return merged


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

    Iterations run **in order**, not all at once, because a ``balanced`` or
    ``finals`` iteration has to seed on the standing *after* the iterations
    before it. Groups inside one iteration are independent games and still fan
    out across the process pool, which is where all the parallelism was anyway:
    a 100-bot field is five groups per variation per iteration.

    ``seeding`` is the standing the run *starts* from — normally the previous
    published board of the same kind, or nothing at all.
    """
    started = time.time()
    outcomes: list[BotOutcome] = []
    errors: list[str] = []

    if not build_jobs(submissions, settings, seeding=seeding):
        return ShowdownResult(started, time.time(), 0, [], [])

    workers = max(1, settings.workers)
    done = 0
    played = 0
    total = 0

    def run(job_list: list[dict]) -> None:
        nonlocal done, played
        if not job_list:
            return
        played += len(job_list)
        if workers == 1 or len(job_list) == 1:
            for job in job_list:
                try:
                    outcomes.extend(BotOutcome(**d) for d in _play_one(job))
                except Exception as exc:  # noqa: BLE001 - one bad group must not stop the rest
                    errors.append(f"variation {job['variation']}: {exc}"[:300])
                done += 1
                if progress:
                    progress(done, total)
            return

        with ProcessPoolExecutor(max_workers=min(workers, len(job_list))) as pool:
            futures = {pool.submit(_play_one, job): job for job in job_list}
            for future in as_completed(futures):
                job = futures[future]
                try:
                    outcomes.extend(BotOutcome(**d) for d in future.result())
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"variation {job['variation']}: {exc}"[:300])
                done += 1
                if progress:
                    progress(done, total)

    for iteration in range(settings.iterations):
        standing = merge_seeding(seeding, seeding_from(outcomes))
        jobs = build_iteration_jobs(submissions, settings, iteration, seeding=standing)

        # Re-estimate what is left every iteration. A `finals` iteration cuts the
        # field to `finals_size`, so it plays far fewer groups than a plan drawn
        # before anything had a score — and a progress bar that ends at 5/6 looks
        # like a run that stopped early.
        total = done + len(jobs) + sum(
            len(build_iteration_jobs(submissions, settings, later, seeding=standing))
            for later in range(iteration + 1, settings.iterations)
        )
        run(jobs)

    rows = aggregate(outcomes)
    return ShowdownResult(started, time.time(), played, rows, errors)


def estimate_seconds(n_bots: int, settings: ShowdownSettings, per_game: float = 15.0) -> float:
    """Rough wall-clock estimate, used to warn the admin before they hit Run."""
    groups = max(1, math.ceil(n_bots / max(1, settings.group_size)))
    games = len(settings.variations) * settings.iterations * groups
    scaled = per_game * (settings.num_rounds / 2000)
    return games * scaled / max(1, settings.workers)
