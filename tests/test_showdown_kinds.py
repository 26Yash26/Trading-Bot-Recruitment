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

import sqlite3

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


def test_migration_adds_kind_to_a_database_that_predates_it(tmp_path):
    """The VM's database holds every real submission and is never recreated, so
    a new column reaches it through `_migrate` or not at all."""
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE showdowns (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "started_at REAL NOT NULL, finished_at REAL, games INTEGER NOT NULL DEFAULT 0, "
        "status TEXT NOT NULL, error TEXT NOT NULL DEFAULT '', "
        "settings TEXT NOT NULL DEFAULT '{}')"
    )
    conn.execute("INSERT INTO showdowns(started_at, status) VALUES(1.0, 'done')")
    conn.commit()

    store._migrate(conn)  # noqa: SLF001 - that is what is under test
    conn.commit()

    columns = {row["name"] for row in conn.execute("PRAGMA table_info(showdowns)")}
    assert "kind" in columns
    row = conn.execute("SELECT kind FROM showdowns").fetchone()
    assert row["kind"] == "practice", "an existing run must not be mislabelled"

    store._migrate(conn)  # noqa: SLF001 - and it must be idempotent
    conn.close()


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
        "server.app.scheduler.trigger_now", lambda kind="practice": triggered.append(kind)
    )
    monkeypatch.setattr("server.app.scheduler.running", False)

    assert as_admin.post("/api/admin/run-now", json={}, headers=ORIGIN).status_code == 200
    body = as_admin.post("/api/admin/run-now", json={"kind": "mock"}, headers=ORIGIN).json()
    assert body["kind"] == "mock"
    assert triggered == ["practice", "mock"]


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
