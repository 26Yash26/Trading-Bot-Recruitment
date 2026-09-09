"""The showdown clock.

Every ``interval_minutes`` (default 120) the whole field plays again and the
leaderboard is replaced. ``next_run_at`` is persisted, so the countdown the
website shows survives a restart or a redeploy instead of silently sliding
forward every time the service bounces.

The showdown itself is CPU-bound and lives in a worker thread, which in turn
fans out to a process pool — the event loop stays free to serve the site while
a hundred bots are playing.
"""

from __future__ import annotations

import asyncio
import time

from harness.evaluate import GROUPINGS, ShowdownSettings, run_showdown
from harness.simulate import BotSpec
from src.auction.capital import CapitalDraw

from . import events, store


def normalise_grouping(value: object) -> str | tuple[str, ...]:
    """A grouping setting from the database, as `ShowdownSettings` wants it.

    Accepts the old single string and the per-iteration list §9 needs, and drops
    anything unrecognised rather than letting a typo in the console raise inside
    the showdown thread — where it would abort the run and leave the board empty.
    """
    if isinstance(value, str):
        return value if value in GROUPINGS else "random"
    if isinstance(value, (list, tuple)):
        modes = tuple(str(m) for m in value if str(m) in GROUPINGS)
        return modes or "random"
    return "random"


class Scheduler:
    def __init__(self) -> None:
        self.running = False
        self.progress = (0, 0)
        self.current_id: int | None = None
        self.last_error = ""
        self._task: asyncio.Task | None = None
        self._wake = asyncio.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop = False
        # What the next run is for. The clock always produces practice runs; an
        # admin pressing "Run mock auction" sets this for one run and it falls
        # back afterwards, so a forgotten switch cannot mislabel the 2am tick.
        self._pending_kind = store.DEFAULT_KIND
        self.kind = store.DEFAULT_KIND

    # -- lifecycle ---------------------------------------------------------

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        settings = store.get_settings()
        if not settings.get("next_run_at"):
            self._schedule_next(settings)
        self._task = asyncio.create_task(self._loop_forever())

    async def stop(self) -> None:
        self._stop = True
        self._wake.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass

    # -- scheduling --------------------------------------------------------

    def _schedule_next(self, settings: dict | None = None) -> float:
        settings = settings or store.get_settings()
        interval = max(1, int(settings.get("interval_minutes", 120))) * 60
        next_at = time.time() + interval
        store.update_settings({"next_run_at": next_at})
        return next_at

    def trigger_now(self, kind: str = store.DEFAULT_KIND) -> None:
        """Admin pressed Run now. ``kind`` labels this one run, not the clock."""
        self._pending_kind = store.normalise_kind(kind)
        store.update_settings({"next_run_at": time.time()})
        if self._loop:
            self._loop.call_soon_threadsafe(self._wake.set)
        else:
            self._wake.set()

    def reschedule(self) -> None:
        """Interval changed — recompute from now and wake the loop."""
        self._schedule_next()
        if self._loop:
            self._loop.call_soon_threadsafe(self._wake.set)
        else:
            self._wake.set()

    def state(self) -> dict:
        settings = store.get_settings()
        done, total = self.progress
        return {
            "running": self.running,
            "kind": self.kind,
            "pending_kind": self._pending_kind,
            "enabled": bool(settings.get("showdown_enabled", True)),
            "interval_minutes": int(settings.get("interval_minutes", 120)),
            "next_run_at": float(settings.get("next_run_at") or 0.0),
            "last_run_at": float(settings.get("last_run_at") or 0.0),
            "progress_done": done,
            "progress_total": total,
            "last_error": self.last_error,
        }

    # -- the loop ----------------------------------------------------------

    async def _loop_forever(self) -> None:
        while not self._stop:
            settings = store.get_settings()
            next_at = float(settings.get("next_run_at") or 0.0)
            wait = max(0.0, next_at - time.time())

            try:
                await asyncio.wait_for(self._wake.wait(), timeout=min(wait, 60.0) or 0.1)
                self._wake.clear()
            except asyncio.TimeoutError:
                pass

            if self._stop:
                return

            settings = store.get_settings()
            due = time.time() >= float(settings.get("next_run_at") or 0.0)
            if not due:
                continue
            if not settings.get("showdown_enabled", True):
                self._schedule_next(settings)
                continue

            try:
                await self.run_once()
            except Exception as exc:  # noqa: BLE001 - the clock must keep ticking
                self.last_error = str(exc)[:300]
            finally:
                self._schedule_next()
                events.publish("schedule", self.state())

    # -- one showdown ------------------------------------------------------

    def collect_field(self, settings: dict) -> dict[int, list[BotSpec]]:
        """Latest accepted file per (roll, variation), minus banned roll numbers."""
        banned = {r.upper() for r in settings.get("banned_rolls", [])}
        field: dict[int, list[BotSpec]] = {}
        for row in store.active_submissions():
            if row["roll"].upper() in banned:
                continue
            variation = int(row["variation"])
            if variation not in settings.get("variations", [1, 2, 3]):
                continue
            field.setdefault(variation, []).append(
                BotSpec(key=row["roll"], path=row["path"], display=row["name"])
            )
        return field

    @staticmethod
    def current_seeding(kind: str) -> dict[int, dict[str, float]]:
        """Per variation: what each bot scored in the last run **of this kind**.

        The kind filter is the whole point. A balanced or finals iteration is
        seeded on cumulative points, and with a practice showdown landing every
        two hours the last finished board is almost always a practice one — so a
        mock auction's snake seeding used to be built from a throwaway run
        against throwaway bounds, silently. A mock seeds on the previous mock;
        the final seeds on the previous final; practice seeds on practice.

        Within one run, iterations seed on each other — see
        `harness.evaluate.run_showdown`. This is only the starting standing.
        """
        seeding: dict[int, dict[str, float]] = {}
        for row in store.leaderboard(kind=kind):
            seeding.setdefault(int(row["variation"]), {})[row["key"]] = float(
                row.get("score", 0.0)
            )
        return seeding

    async def run_once(self) -> dict:
        if self.running:
            return {"status": "already-running"}

        settings = store.get_settings()
        field = self.collect_field(settings)
        if not any(field.values()):
            store.update_settings({"last_run_at": time.time()})
            return {"status": "no-submissions"}

        show_settings = ShowdownSettings(
            variations=tuple(settings.get("variations", [1, 2])),
            num_rounds=int(settings.get("num_rounds", 2000)),
            block_size=int(settings.get("block_size", 500)),
            group_size=int(settings.get("group_size", 20)),
            iterations=int(settings.get("iterations", 3)),
            grouping=normalise_grouping(settings.get("grouping", "random")),
            finals_size=int(settings.get("finals_size", 20)),
            capital=CapitalDraw.from_settings(settings),
            block_bounds=tuple(tuple(b) for b in settings.get("block_bounds")),
            seed=int(settings.get("seed", 20260916)) + int(time.time()) % 100000,
            workers=int(settings.get("workers", 4)),
            round_timeout=float(settings.get("round_timeout", 1.0)),
            mem_mb=int(settings.get("mem_mb", 512)),
        )

        kind = self._pending_kind
        self._pending_kind = store.DEFAULT_KIND

        self.running = True
        self.kind = kind
        self.last_error = ""
        self.progress = (0, 0)
        showdown_id = store.start_showdown(settings, kind=kind)
        self.current_id = showdown_id
        loop = asyncio.get_running_loop()
        events.publish("showdown", {"status": "started", "id": showdown_id, "kind": kind})

        def on_progress(done: int, total: int) -> None:
            self.progress = (done, total)
            events.publish_threadsafe(loop, "progress", {"done": done, "total": total})

        try:
            # A balanced or finals iteration needs a standing to seed on (§9).
            # If every iteration in this run is random there is nothing to seed.
            modes = set(show_settings.grouping_schedule())
            seeding = None if modes == {"random"} else self.current_seeding(kind)
            result = await loop.run_in_executor(
                None,
                lambda: run_showdown(
                    field, show_settings, progress=on_progress, seeding=seeding
                ),
            )
            store.finish_showdown(
                showdown_id,
                games=result.games_played,
                rows=[r.as_dict() for r in result.rows],
                error="; ".join(result.errors)[:500],
            )
            store.update_settings({"last_run_at": time.time()})
            self.last_error = "; ".join(result.errors)[:300]
            store.audit(
                "scheduler", "showdown",
                f"id={showdown_id} kind={kind} games={result.games_played}",
            )
            events.publish("leaderboard", store.leaderboard())
            return {"status": "done", "id": showdown_id, "games": result.games_played}
        except Exception as exc:  # noqa: BLE001
            store.finish_showdown(showdown_id, games=0, rows=[], error=str(exc)[:500])
            self.last_error = str(exc)[:300]
            raise
        finally:
            self.running = False
            self.kind = store.DEFAULT_KIND
            self.current_id = None
            self.progress = (0, 0)
            events.publish(
                "showdown", {"status": "finished", "id": showdown_id, "kind": kind}
            )


scheduler = Scheduler()
