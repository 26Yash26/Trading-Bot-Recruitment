"""Mock, practice and final runs are different things, and the code must know it.

Before showdowns carried a `kind`, three separate problems shared one cause:

  * the 2-hourly practice run silently replaced a published mock board;
  * `Scheduler.current_seeding` read whatever finished last, so a mock auction's
    snake seeding was built from a practice run against throwaway bounds;
  * nothing distinguished the graded run from the hundreds before it.

These tests pin the distinction, and the per-iteration grouping that lets one
run play the whole of §9 rather than needing three sequential ones.
"""

from __future__ import annotations

import json
import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

from harness.evaluate import (
    GROUPINGS,
    ShowdownSettings,
    build_iteration_jobs,
    build_jobs,
    merge_seeding,
    seeding_from,
)
from harness.simulate import BotOutcome, BotSpec
from server import config, store
from server.app import app
from server.scheduler import Scheduler, normalise_grouping

REPO_ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent
SAMPLE_BOT = REPO_ROOT / "starter-kit" / "sample_bots" / "sample_bot_1.py"

ORIGIN = {"Origin": "http://localhost:8000"}


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def as_admin():
    store.upsert_user("admin@smail.iitm.ac.in", "Test Admin", "")
    token, _ = store.create_session("admin@smail.iitm.ac.in")
    test_client = TestClient(app)
    test_client.cookies.set(config.COOKIE_NAME, token)
    with test_client as c:
        yield c


@pytest.fixture
def finished_showdowns():
    """One finished run of each kind, cleaned up afterwards."""
    ids = {}
    for kind in store.SHOWDOWN_KINDS:
        showdown_id = store.start_showdown({"marker": kind}, kind=kind)
        store.finish_showdown(
            showdown_id,
            games=3,
            rows=[{"key": f"BOT{kind.upper()}", "variation": 1, "score": 100.0, "rank": 1}],
        )
        ids[kind] = showdown_id
    yield ids
    with store._lock:  # noqa: SLF001 - test teardown owns the connection
        conn = store.connect()
        marks = tuple(ids.values())
        holes = ",".join("?" * len(marks))
        conn.execute(f"DELETE FROM results WHERE showdown_id IN ({holes})", marks)
        conn.execute(f"DELETE FROM showdowns WHERE id IN ({holes})", marks)
        conn.commit()


# --- the store knows what a run was for ----------------------------------------


def test_kind_defaults_to_practice_and_rejects_nonsense():
    assert store.normalise_kind("mock") == "mock"
    assert store.normalise_kind("FINAL") == "final"
    assert store.normalise_kind("") == store.DEFAULT_KIND
    assert store.normalise_kind("graded") == store.DEFAULT_KIND
    assert store.normalise_kind(None) == store.DEFAULT_KIND


def test_latest_showdown_can_be_restricted_to_a_kind(finished_showdowns):
    for kind, showdown_id in finished_showdowns.items():
        assert store.latest_showdown(kind=kind)["id"] == showdown_id
    # No kind means "whatever ran last", which is what the live board wants.
    assert store.latest_showdown()["id"] == max(finished_showdowns.values())


def test_published_showdowns_leave_out_practice_runs(finished_showdowns):
    published = {row["id"]: row["kind"] for row in store.published_showdowns()}
    assert finished_showdowns["mock"] in published
    assert finished_showdowns["final"] in published
    assert finished_showdowns["practice"] not in published, (
        "a practice board is rewritten every interval and means nothing; "
        "listing it buries the boards that do"
    )


def test_a_practice_run_does_not_bury_the_mock_board(finished_showdowns):
    """The whole point: the mock board survives the next practice run."""
    rows = store.leaderboard(finished_showdowns["mock"])
    assert [r["key"] for r in rows] == ["BOTMOCK"]


#: The `showdowns` table exactly as it shipped before `kind` existed, the shape
#: the VM's live database is in when a deploy carrying `kind` lands on it.
PRE_KIND_SHOWDOWNS = """
CREATE TABLE showdowns (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  REAL NOT NULL,
    finished_at REAL,
    games       INTEGER NOT NULL DEFAULT 0,
    status      TEXT NOT NULL,
    error       TEXT NOT NULL DEFAULT '',
    settings    TEXT NOT NULL DEFAULT '{}'
);
INSERT INTO showdowns(started_at, finished_at, status) VALUES(1.0, 2.0, 'done');
"""


def _open_pre_kind_database(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(PRE_KIND_SHOWDOWNS)
    conn.commit()
    return conn


def test_startup_upgrades_a_database_that_predates_kind(tmp_path):
    """The whole startup path, in the order `connect()` runs it, against a live-
    shaped database.

    This is the test that was missing, and it cost an outage. The `kind` index
    was declared inside SCHEMA, and SCHEMA runs BEFORE `_migrate`. On a database
    that already has the table, `CREATE TABLE IF NOT EXISTS` is a no-op, so the
    column did not exist yet and `CREATE INDEX ... ON showdowns(kind, ...)` blew
    up with "no such column: kind", aborting `executescript` and taking the API
    down on deploy. Every test passed, because every test database is created
    fresh, where the table is built WITH the column and the ordering never
    matters. Only an upgraded database can catch it, so build one.
    """
    conn = _open_pre_kind_database(tmp_path / "old.db")

    # Exactly what `store.connect()` does, in order.
    conn.executescript(store.SCHEMA)
    store._migrate(conn)  # noqa: SLF001 - that is what is under test
    conn.commit()

    columns = {row["name"] for row in conn.execute("PRAGMA table_info(showdowns)")}
    assert "kind" in columns
    indexes = {row["name"] for row in conn.execute("PRAGMA index_list(showdowns)")}
    assert "idx_showdowns_kind" in indexes, "the index never got created"

    row = conn.execute("SELECT kind FROM showdowns").fetchone()
    assert row["kind"] == "practice", "an existing run must not be mislabelled"

    # Restarts re-run both, so both have to be idempotent.
    conn.executescript(store.SCHEMA)
    store._migrate(conn)  # noqa: SLF001
    conn.commit()
    conn.close()


def test_schema_alone_never_references_a_migrated_column(tmp_path):
    """Belt and braces, and the rule stated as a test: SCHEMA must apply to an
    old database on its own. Anything needing a migrated column goes in INDEXES.
    """
    conn = _open_pre_kind_database(tmp_path / "old2.db")
    conn.executescript(store.SCHEMA)   # must not raise
    conn.close()


def test_every_migrated_column_is_actually_in_the_table_definition():
    """`MIGRATIONS` upgrades old databases; `SCHEMA` builds new ones. If a column
    is in one and not the other, fresh and upgraded deployments disagree."""
    for table, column, _ in store.MIGRATIONS:
        start = store.SCHEMA.index(f"CREATE TABLE IF NOT EXISTS {table}")
        body = store.SCHEMA[start : store.SCHEMA.index(");", start)]
        assert column in body, (
            f"{table}.{column} is migrated onto old databases but missing from "
            "SCHEMA, so a fresh deployment would never have it"
        )


# --- seeding reads the right board ---------------------------------------------


def test_seeding_reads_the_last_run_of_the_same_kind(finished_showdowns):
    """A mock seeds on the previous mock, not on the practice run that landed
    twenty minutes ago against throwaway bounds."""
    assert Scheduler.current_seeding("mock") == {1: {"BOTMOCK": 100.0}}
    assert Scheduler.current_seeding("final") == {1: {"BOTFINAL": 100.0}}
    assert Scheduler.current_seeding("practice") == {1: {"BOTPRACTICE": 100.0}}


def test_seeding_helpers_accumulate_across_iterations():
    outcomes = [
        BotOutcome(key="A", variation=1, starting_capital=0, final_capital=0,
                   net_profit=0, wins=0, rounds_played=0, iteration_score=210.0),
        BotOutcome(key="A", variation=1, starting_capital=0, final_capital=0,
                   net_profit=0, wins=0, rounds_played=0, iteration_score=190.0),
        BotOutcome(key="B", variation=2, starting_capital=0, final_capital=0,
                   net_profit=0, wins=0, rounds_played=0, iteration_score=50.0),
    ]
    assert seeding_from(outcomes) == {1: {"A": 400.0}, 2: {"B": 50.0}}
    assert merge_seeding({1: {"A": 5.0}}, {1: {"A": 2.0, "C": 1.0}}) == {
        1: {"A": 7.0, "C": 1.0}
    }
    assert merge_seeding(None, None) == {}


# --- per-iteration grouping ----------------------------------------------------


def test_a_single_mode_applies_to_every_iteration():
    settings = ShowdownSettings(grouping="balanced", iterations=4)
    assert [settings.grouping_for_iteration(i) for i in range(4)] == ["balanced"] * 4


def test_a_schedule_holds_its_last_entry_rather_than_cycling():
    """Cycling is right for block bounds and wrong here: it would throw a seeded
    field back into a random draw after it had been seeded."""
    settings = ShowdownSettings(grouping=("random", "balanced"), iterations=5)
    assert [settings.grouping_for_iteration(i) for i in range(5)] == [
        "random", "balanced", "balanced", "balanced", "balanced",
    ]


def test_the_ps9_schedule_is_expressible_in_one_run():
    settings = ShowdownSettings(
        grouping=("random", "random", "balanced", "finals", "finals"), iterations=5
    )
    assert [settings.grouping_for_iteration(i) for i in range(5)] == [
        "random", "random", "balanced", "finals", "finals",
    ]


@pytest.mark.parametrize("bad", ("snake", ("random", "snake"), ()))
def test_an_unknown_grouping_mode_is_refused(bad):
    with pytest.raises(ValueError):
        ShowdownSettings(grouping=bad).grouping_schedule()


def test_jobs_carry_the_grouping_of_their_own_iteration():
    specs = {1: [BotSpec(key=f"R{i}", path=SAMPLE_BOT) for i in range(20)]}
    settings = ShowdownSettings(
        variations=(1,), iterations=3, grouping=("random", "random", "balanced")
    )
    assert [j["grouping"] for j in build_jobs(specs, settings)] == [
        "random", "random", "balanced",
    ]


def test_a_finals_iteration_cuts_the_field_on_the_standing_it_is_given():
    specs = {1: [BotSpec(key=f"R{i}", path=SAMPLE_BOT) for i in range(40)]}
    settings = ShowdownSettings(
        variations=(1,), iterations=1, grouping="finals", finals_size=5, group_size=20
    )
    standing = {1: {f"R{i}": float(i) for i in range(40)}}
    jobs = build_iteration_jobs(specs, settings, 0, seeding=standing)

    entered = {key for job in jobs for key, _ in job["specs"]}
    assert entered == {"R39", "R38", "R37", "R36", "R35"}


def test_normalise_grouping_survives_whatever_is_in_the_database():
    assert normalise_grouping("balanced") == "balanced"
    assert normalise_grouping(["random", "finals"]) == ("random", "finals")
    # A typo in the console must not raise inside the showdown thread, where it
    # would abort the run and leave the board empty.
    assert normalise_grouping("snake") == "random"
    assert normalise_grouping(["snake"]) == "random"
    assert normalise_grouping(None) == "random"
    for mode in GROUPINGS:
        assert normalise_grouping(mode) == mode


# --- the API -------------------------------------------------------------------


def test_run_now_defaults_to_practice_and_accepts_a_kind(as_admin, monkeypatch):
    triggered = []
    monkeypatch.setattr(
        "server.app.scheduler.trigger_now",
        lambda kind="practice", variations=None: triggered.append((kind, variations)),
    )
    monkeypatch.setattr("server.app.scheduler.running", False)

    assert as_admin.post("/api/admin/run-now", json={}, headers=ORIGIN).status_code == 200
    body = as_admin.post("/api/admin/run-now", json={"kind": "mock"}, headers=ORIGIN).json()
    assert body["kind"] == "mock"
    assert triggered == [("practice", None), ("mock", None)]


def test_run_now_can_cover_one_variation_at_a_time(as_admin, monkeypatch):
    """Replaying variation 1 must not disturb the others."""
    triggered = []
    monkeypatch.setattr(
        "server.app.scheduler.trigger_now",
        lambda kind="practice", variations=None: triggered.append((kind, variations)),
    )
    monkeypatch.setattr("server.app.scheduler.running", False)
    before = store.get_settings()["variations"]
    try:
        store.update_settings({"variations": [1, 2]})
        body = as_admin.post(
            "/api/admin/run-now", json={"kind": "mock", "variations": [1]}, headers=ORIGIN
        ).json()
        assert body["variations"] == [1]
        assert triggered == [("mock", (1,))]
    finally:
        store.update_settings({"variations": before})


def test_run_now_refuses_a_variation_that_is_not_released(as_admin):
    """Otherwise a run silently plays nobody and looks like a broken showdown."""
    before = store.get_settings()["variations"]
    try:
        store.update_settings({"variations": [1, 2]})
        response = as_admin.post(
            "/api/admin/run-now", json={"variations": [4]}, headers=ORIGIN
        )
        assert response.status_code == 400
        assert "not released" in response.json()["detail"]

        for bad in ([], "1", [1, "x"]):
            assert as_admin.post(
                "/api/admin/run-now", json={"variations": bad}, headers=ORIGIN
            ).status_code == 400
    finally:
        store.update_settings({"variations": before})


def test_collect_field_narrows_to_the_chosen_variations():
    settings = {"variations": [1, 2, 3], "banned_rolls": []}
    everything = Scheduler().collect_field(settings)
    narrowed = Scheduler().collect_field(settings, (1,))
    assert set(narrowed) <= {1}
    assert set(narrowed) <= set(everything)


def test_run_now_refuses_a_kind_it_does_not_know(as_admin):
    response = as_admin.post("/api/admin/run-now", json={"kind": "graded"}, headers=ORIGIN)
    assert response.status_code == 400
    assert "practice" in response.json()["detail"]


def test_grouping_setting_accepts_a_list_and_refuses_rubbish(as_admin):
    before = store.get_settings()["grouping"]
    try:
        ok = as_admin.patch(
            "/api/admin/settings", json={"grouping": ["random", "balanced"]}, headers=ORIGIN
        )
        assert ok.status_code == 200
        assert store.get_settings()["grouping"] == ["random", "balanced"]

        for bad in ("snake", ["snake"], [], 3):
            assert as_admin.patch(
                "/api/admin/settings", json={"grouping": bad}, headers=ORIGIN
            ).status_code == 400
    finally:
        store.update_settings({"grouping": before})


def test_published_boards_are_listed_and_addressable(client, finished_showdowns):
    listed = {row["id"] for row in client.get("/api/showdowns").json()["showdowns"]}
    assert finished_showdowns["mock"] in listed

    response = client.get(f"/api/leaderboard?showdown={finished_showdowns['mock']}")
    assert response.status_code == 200
    assert response.json()["showdown"]["kind"] == "mock"
    assert [r["key"] for r in response.json()["rows"]] == ["BOTMOCK"]


def test_a_practice_board_is_not_addressable_by_id(client, finished_showdowns):
    """Hundreds of them exist and none means anything; handing out an id invites
    a stale link being passed around as a result."""
    response = client.get(f"/api/leaderboard?showdown={finished_showdowns['practice']}")
    assert response.status_code == 404


def test_state_carries_the_published_boards(client, finished_showdowns):
    body = client.get("/api/state").json()
    ids = {row["id"] for row in body["published_showdowns"]}
    assert finished_showdowns["mock"] in ids
    assert body["last_showdown"]["kind"] in store.SHOWDOWN_KINDS


# --- one run plays the whole tournament ----------------------------------------


def test_a_balanced_iteration_seeds_on_earlier_iterations_of_the_same_run(monkeypatch):
    """The reason iterations run in order rather than all at once.

    A balanced iteration snake-seeds on cumulative points. If every iteration
    were planned up front it could only seed on some previously *published*
    board, which is the bug this replaced: with a 2-hourly practice clock that
    board is almost never the one you meant.
    """
    import harness.evaluate as ev

    scores = {f"R{i}": float(i) for i in range(40)}
    seen: list[dict] = []

    def fake_play(job):
        seen.append(job)
        return [
            {
                "key": key, "variation": job["variation"], "starting_capital": 0.0,
                "final_capital": 0.0, "net_profit": 0.0, "wins": 0, "rounds_played": 1,
                "iteration_score": scores[key],
            }
            for key, _ in job["specs"]
        ]

    monkeypatch.setattr(ev, "_play_one", fake_play)

    specs = {1: [BotSpec(key=f"R{i}", path=SAMPLE_BOT) for i in range(40)]}
    settings = ShowdownSettings(
        variations=(1,), iterations=3, workers=1, group_size=20,
        grouping=("random", "random", "balanced"),
    )
    result = ev.run_showdown(specs, settings)

    # The two random iterations gave every bot 2 x its own score.
    row = {r.key: r.score for r in result.rows}
    assert row["R39"] == pytest.approx(39.0 * 3)

    balanced = [job for job in seen if job["grouping"] == "balanced"]
    assert len(balanced) == 2, "40 bots, groups of 20"

    # Snake seeding deals rank 1 and rank 2 into DIFFERENT groups, so the two
    # groups end up close in average strength. A random draw would not do that
    # reliably, and seeding on nothing could not do it at all.
    groups = [{key for key, _ in job["specs"]} for job in balanced]
    assert sum("R39" in g for g in groups) == 1
    means = sorted(sum(scores[k] for k in g) / len(g) for g in groups)
    assert means[1] - means[0] < 1.0, f"groups are not strength-balanced: {means}"


def test_an_all_random_run_never_asks_for_a_standing(monkeypatch):
    """A practice run on random grouping must not touch the board at all."""
    settings = ShowdownSettings(grouping="random", iterations=3)
    assert set(settings.grouping_schedule()) == {"random"}


def test_progress_finishes_at_one_hundred_percent_when_the_finals_cut(monkeypatch):
    """A `finals` iteration plays far fewer groups than a plan drawn before
    anything had a score, so the total has to be re-estimated as the run goes.
    A bar that stops at 5/6 looks exactly like a run that died."""
    import harness.evaluate as ev

    scores = {f"R{i}": float(i) for i in range(40)}
    monkeypatch.setattr(
        ev, "_play_one",
        lambda job: [
            {"key": k, "variation": job["variation"], "starting_capital": 0.0,
             "final_capital": 0.0, "net_profit": 0.0, "wins": 0, "rounds_played": 1,
             "iteration_score": scores[k]}
            for k, _ in job["specs"]
        ],
    )

    trail: list[tuple[int, int]] = []
    specs = {1: [BotSpec(key=f"R{i}", path=SAMPLE_BOT) for i in range(40)]}
    settings = ShowdownSettings(
        variations=(1,), iterations=4, workers=1, group_size=20, finals_size=20,
        grouping=("random", "random", "balanced", "finals"),
    )
    result = ev.run_showdown(specs, settings, progress=lambda d, t: trail.append((d, t)))

    done, total = trail[-1]
    assert done == total == result.games_played
    # Two groups per random/balanced iteration, one for the cut-down finals.
    assert result.games_played == 7


# --- the default is the whole tournament ---------------------------------------


def test_a_showdown_is_the_whole_tournament_by_default():
    """Five iterations: two random, one strength balanced, then two finals.
    That is what a showdown means, and it is the shipped default rather than
    something an admin has to assemble."""
    grouping = store.DEFAULT_SETTINGS["grouping"]
    assert grouping == ["random", "random", "balanced", "finals", "finals"]
    assert store.DEFAULT_SETTINGS["iterations"] == len(grouping)

    settings = ShowdownSettings(
        grouping=normalise_grouping(grouping),
        iterations=store.DEFAULT_SETTINGS["iterations"],
    )
    assert [settings.grouping_for_iteration(i) for i in range(5)] == grouping


def test_a_default_run_consults_a_standing():
    """The regression this guards: if the default were plain "random", a mock
    would silently play blind groups and the tournament structure the rules page
    advertises would never actually run."""
    settings = ShowdownSettings(grouping=normalise_grouping(store.DEFAULT_SETTINGS["grouping"]))
    assert set(settings.grouping_schedule()) != {"random"}


def test_bounds_mode_is_validated_at_the_admin_door(as_admin):
    before = store.get_settings()["bounds_mode"]
    try:
        assert as_admin.patch(
            "/api/admin/settings", json={"bounds_mode": "fixed"}, headers=ORIGIN
        ).status_code == 200
        assert store.get_settings()["bounds_mode"] == "fixed"
        assert as_admin.patch(
            "/api/admin/settings", json={"bounds_mode": "sometimes"}, headers=ORIGIN
        ).status_code == 400
    finally:
        store.update_settings({"bounds_mode": before})


def test_random_is_the_shipped_default_for_bounds():
    assert store.DEFAULT_SETTINGS["bounds_mode"] == "random"


# --- one variation at a time -----------------------------------------------------


@pytest.fixture
def two_runs():
    """An older run scoring variations 1 and 2, then a newer one scoring only 1.

    The shape a per-variation replay leaves behind, and the case the live board
    has to get right.
    """
    old = store.start_showdown({}, kind="practice")
    store.finish_showdown(old, games=2, rows=[
        {"key": "OLD1", "variation": 1, "score": 10.0, "rank": 1},
        {"key": "OLD2", "variation": 2, "score": 20.0, "rank": 1},
    ])
    time.sleep(0.01)
    new = store.start_showdown({}, kind="practice")
    store.finish_showdown(new, games=1, rows=[
        {"key": "NEW1", "variation": 1, "score": 30.0, "rank": 1},
    ])
    yield old, new
    with store._lock:  # noqa: SLF001 - test teardown owns the connection
        conn = store.connect()
        conn.execute("DELETE FROM results WHERE showdown_id IN (?,?)", (old, new))
        conn.execute("DELETE FROM showdowns WHERE id IN (?,?)", (old, new))
        conn.commit()


def test_replaying_one_variation_leaves_the_others_standing(two_runs):
    """Without this, running variation 1 on its own wiped variation 2 off the
    site: the board was whatever the single newest run happened to contain."""
    board = {row["variation"]: row["key"] for row in store.leaderboard()}
    assert board[1] == "NEW1", "variation 1 should show the newer run"
    assert board[2] == "OLD2", "variation 2 should still show the older run"


def test_naming_a_showdown_still_returns_exactly_that_board(two_runs):
    old, _ = two_runs
    rows = store.leaderboard(old)
    assert {r["key"] for r in rows} == {"OLD1", "OLD2"}


def test_latest_run_per_variation_picks_the_newest_of_each(two_runs):
    old, new = two_runs
    assert store.latest_run_per_variation() == {1: new, 2: old}


# --- settings written by an older build ------------------------------------------


def test_a_stored_string_grouping_is_upgraded_to_a_schedule(tmp_path):
    """`get_settings` overlays the defaults with whatever is stored, so a value
    saved once wins forever. When the SHAPE of a setting changes the stored one
    has to be rewritten, or the new default never takes effect.

    This bit in production: the live database held `grouping = "finals"` from
    the single-mode era, which means every iteration cuts the field to the
    leaders and a bot outside the top `finals_size` never plays at all.
    """
    conn = sqlite3.connect(tmp_path / "settings.db")
    conn.row_factory = sqlite3.Row
    conn.executescript(store.SCHEMA)
    conn.execute("INSERT INTO settings(key, value) VALUES('grouping', ?)",
                 (json.dumps("finals"),))
    conn.execute("INSERT INTO settings(key, value) VALUES('iterations', ?)",
                 (json.dumps(3),))
    conn.commit()

    store._migrate(conn)  # noqa: SLF001 - that is what is under test
    conn.commit()

    stored = {r["key"]: json.loads(r["value"])
              for r in conn.execute("SELECT key, value FROM settings")}
    assert stored["grouping"] == store.DEFAULT_SETTINGS["grouping"]
    assert stored["iterations"] == len(store.DEFAULT_SETTINGS["grouping"])
    conn.close()


def test_a_stored_schedule_is_left_alone(tmp_path):
    """Only the old string shape is rewritten. An admin's own schedule stands."""
    conn = sqlite3.connect(tmp_path / "settings2.db")
    conn.row_factory = sqlite3.Row
    conn.executescript(store.SCHEMA)
    mine = ["random", "balanced", "balanced"]
    conn.execute("INSERT INTO settings(key, value) VALUES('grouping', ?)",
                 (json.dumps(mine),))
    conn.commit()

    store._migrate(conn)  # noqa: SLF001
    conn.commit()

    row = conn.execute("SELECT value FROM settings WHERE key='grouping'").fetchone()
    assert json.loads(row["value"]) == mine
    conn.close()


# --- no live board: only mock rounds and the finals ------------------------------


def test_practice_runs_are_invisible_to_participants(finished_showdowns):
    """There is no rolling board. A practice run is a private rehearsal, so it
    must not reach the public leaderboard, the archive, or `/api/state`."""
    public = store.leaderboard(kinds=store.PUBLISHED_KINDS)
    assert "BOTPRACTICE" not in {row["key"] for row in public}
    assert {"BOTMOCK", "BOTFINAL"} & {row["key"] for row in public}


def test_the_public_state_reports_the_last_PUBLISHED_run(client, finished_showdowns):
    body = client.get("/api/state").json()
    assert body["last_showdown"]["kind"] in store.PUBLISHED_KINDS
    assert body["last_showdown"]["id"] != finished_showdowns["practice"]


def test_the_public_leaderboard_never_serves_a_rehearsal(client, finished_showdowns):
    rows = client.get("/api/leaderboard").json()["rows"]
    assert "BOTPRACTICE" not in {row["key"] for row in rows}


def test_the_clock_is_off_by_default():
    """Nothing runs on a timer any more; a showdown is an announced event."""
    assert store.DEFAULT_SETTINGS["showdown_enabled"] is False


def test_seeding_still_sees_rehearsals(finished_showdowns):
    """Publishing and seeding are different questions. A practice run is hidden
    from participants but still seeds the next practice run."""
    assert Scheduler.current_seeding("practice") == {1: {"BOTPRACTICE": 100.0}}


# --- deleting a board ------------------------------------------------------------


def test_deleting_a_board_removes_it_and_its_results():
    showdown = store.start_showdown({}, kind="mock")
    store.finish_showdown(showdown, games=1, rows=[
        {"key": "GONE", "variation": 1, "score": 1.0, "rank": 1},
    ])
    assert store.leaderboard(showdown)

    removed = store.delete_showdown(showdown)
    assert removed["id"] == showdown and removed["kind"] == "mock"
    assert store.leaderboard(showdown) == []
    assert showdown not in {r["id"] for r in store.published_showdowns()}
    assert store.delete_showdown(showdown) is None, "deleting twice must be a no-op"


def test_deleting_the_newest_board_makes_the_previous_one_current():
    """What an organiser actually wants from delete: undo a bad round."""
    first = store.start_showdown({}, kind="mock")
    store.finish_showdown(first, games=1, rows=[
        {"key": "KEEP", "variation": 1, "score": 5.0, "rank": 1},
    ])
    time.sleep(0.01)
    second = store.start_showdown({}, kind="mock")
    store.finish_showdown(second, games=1, rows=[
        {"key": "OOPS", "variation": 1, "score": 9.0, "rank": 1},
    ])
    try:
        board = {r["key"] for r in store.leaderboard(kinds=store.PUBLISHED_KINDS)
                 if r["variation"] == 1}
        assert board == {"OOPS"}

        store.delete_showdown(second)
        board = {r["key"] for r in store.leaderboard(kinds=store.PUBLISHED_KINDS)
                 if r["variation"] == 1}
        assert board == {"KEEP"}, "the round before it should be current again"
        # And it is the standing the next mock seeds on.
        assert Scheduler.current_seeding("mock") == {1: {"KEEP": 5.0}}
    finally:
        store.delete_showdown(first)


def test_the_delete_endpoint_is_admin_only_and_audited(as_admin, client):
    showdown = store.start_showdown({}, kind="mock")
    store.finish_showdown(showdown, games=1, rows=[
        {"key": "X", "variation": 1, "score": 1.0, "rank": 1},
    ])
    try:
        assert client.delete(f"/api/admin/showdowns/{showdown}").status_code in (401, 403)
        assert as_admin.delete(
            f"/api/admin/showdowns/{showdown}", headers=ORIGIN
        ).status_code == 200
        assert as_admin.delete(
            f"/api/admin/showdowns/{showdown}", headers=ORIGIN
        ).status_code == 404
        detail = " ".join(r["detail"] for r in store.audit_log(20)
                          if r["action"] == "delete-showdown")
        assert f"id={showdown}" in detail
    finally:
        store.delete_showdown(showdown)


def test_a_running_showdown_cannot_be_deleted(as_admin, monkeypatch):
    """Its result rows are still being written."""
    showdown = store.start_showdown({}, kind="mock")
    try:
        monkeypatch.setattr("server.app.scheduler.running", True)
        monkeypatch.setattr("server.app.scheduler.current_id", showdown)
        response = as_admin.delete(f"/api/admin/showdowns/{showdown}", headers=ORIGIN)
        assert response.status_code == 409
        assert store.showdown_history(50)
    finally:
        store.delete_showdown(showdown)


def test_run_now_works_while_the_clock_is_off(monkeypatch):
    """`showdown_enabled` gates the timer, not the button.

    Turning the clock off (there is no rolling board) also silently disabled
    Run now: the scheduler loop skipped every due run when the setting was
    false, manual or not, so nothing could be started at all.
    """
    sched = Scheduler()
    assert sched._manual is False  # noqa: SLF001
    sched.trigger_now("mock", (1,))
    assert sched._manual is True, "a manual request must be distinguishable"  # noqa: SLF001
    assert sched.state()["pending_kind"] == "mock"


def test_the_clock_still_gates_unattended_runs():
    """With no manual request pending, a disabled clock stays quiet."""
    sched = Scheduler()
    settings = dict(store.DEFAULT_SETTINGS)
    assert settings["showdown_enabled"] is False
    assert sched._manual is False  # noqa: SLF001
