"""The web layer: what is public, what is gated, and what is never served.

The path tests are the important ones. `/var/www/html` on the VM is a checkout of
this entire private repo, so "does a request path ever become a file path" is
the question that decides whether `secret/` is on the internet.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from server import config, store
from server.app import app

ORIGIN = {"Origin": "http://localhost:8000"}


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def _signed_in_client(email: str, name: str, roll: str) -> TestClient:
    store.upsert_user(email, name, roll)
    token, _ = store.create_session(email)
    test_client = TestClient(app)
    test_client.cookies.set(config.COOKIE_NAME, token)
    return test_client


@pytest.fixture
def as_user():
    """A signed-in participant."""
    with _signed_in_client("me24b152@smail.iitm.ac.in", "Test Participant", "ME24B152") as c:
        yield c


@pytest.fixture
def as_admin():
    with _signed_in_client("admin@smail.iitm.ac.in", "Test Admin", "") as c:
        yield c


# --- public surface ------------------------------------------------------------


def test_state_is_public(client):
    body = client.get("/api/state").json()
    assert "schedule" in body
    assert body["num_rounds"] == 2000


def test_leaderboard_is_public(client):
    assert client.get("/api/leaderboard").status_code == 200


def test_state_never_leaks_the_hidden_distribution(client):
    """`block_bounds` and `seed` decide the game; a participant must not see them."""
    body = client.get("/api/state").json()
    assert "block_bounds" not in body
    assert "seed" not in body
    assert "block_bounds" not in store.public_settings()
    assert "seed" not in store.public_settings()


def test_security_headers_are_set(client):
    headers = client.get("/").headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert "default-src 'self'" in headers["content-security-policy"]
    assert "'unsafe-inline'" not in headers["content-security-policy"]


# --- nothing on disk is reachable ----------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/secret/config.py",
        "/server/config.py",
        "/server/store.py",
        "/harness/evaluate.py",
        "/sandbox/runner.py",
        "/scripts/seed_demo.py",
        "/.git/config",
        "/.env",
        "/.local/quantguild.db",
        "/web/../../etc/passwd",
        "/%2e%2e/secret/config.py",
    ],
)
def test_no_request_path_becomes_a_file_path(client, path):
    """Every one of these renders the SPA shell instead of a file.

    The route is an allowlist — `/web/` and `/public/` are mounted, and
    everything else returns index.html without consulting the filesystem — so
    traversal has nothing to traverse.
    """
    response = client.get(path)
    assert response.status_code in (200, 404)
    if response.status_code == 200:
        assert response.text.lstrip().startswith("<!DOCTYPE html>")
        assert "GOOGLE_CLIENT_SECRET" not in response.text
        assert "BLOCK_BOUNDS" not in response.text


def test_static_assets_are_served(client):
    assert client.get("/web/css/app.css").status_code == 200
    assert client.get("/web/js/main.js").status_code == 200


# --- authentication ------------------------------------------------------------


def test_me_is_anonymous_without_a_session(client):
    assert client.get("/api/me").json()["signed_in"] is False


def test_me_reports_the_signed_in_user(as_user):
    body = as_user.get("/api/me").json()
    assert body["signed_in"] is True
    assert body["roll"] == "ME24B152"
    assert body["is_admin"] is False


def test_submitting_requires_a_session(client):
    response = client.post("/api/submit", files={"file": ("ME24B152_1.py", b"x")}, headers=ORIGIN)
    assert response.status_code == 401


def test_login_rejects_a_forged_oauth_state(client):
    """Without the state cookie the callback must refuse, or anyone with a link
    could complete a sign-in on someone else's behalf."""
    response = client.get(
        "/api/auth/callback?code=abc&state=attacker", follow_redirects=False
    )
    assert response.status_code == 302
    assert "auth=failed" in response.headers["location"]
    assert "reason=state" in response.headers["location"]


# --- admin ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "method, path",
    [
        ("get", "/api/admin/settings"),
        ("get", "/api/admin/submissions"),
        ("get", "/api/admin/audit"),
        ("post", "/api/admin/run-now"),
    ],
)
def test_admin_routes_reject_anonymous(client, method, path):
    assert getattr(client, method)(path, headers=ORIGIN).status_code == 401


@pytest.mark.parametrize(
    "method, path",
    [
        ("get", "/api/admin/settings"),
        ("post", "/api/admin/run-now"),
    ],
)
def test_admin_routes_reject_a_normal_user(as_user, method, path):
    response = getattr(as_user, method)(path, headers=ORIGIN)
    assert response.status_code == 403


def test_admin_can_read_and_change_settings(as_admin):
    body = as_admin.get("/api/admin/settings").json()
    assert body["settings"]["interval_minutes"] == 120
    assert body["isolation"] in {"docker", "bwrap", "unshare", "sudo", "plain"}

    response = as_admin.patch(
        "/api/admin/settings", json={"interval_minutes": 45}, headers=ORIGIN
    )
    assert response.status_code == 200
    assert response.json()["settings"]["interval_minutes"] == 45
    store.update_settings({"interval_minutes": 120})


def test_unknown_settings_keys_are_ignored(as_admin):
    """A typo — or an attempt to inject a new key — must not enter the table."""
    as_admin.patch(
        "/api/admin/settings",
        json={"totally_made_up": "value", "interval_minutes": 90},
        headers=ORIGIN,
    )
    settings = store.get_settings()
    assert "totally_made_up" not in settings
    assert settings["interval_minutes"] == 90
    store.update_settings({"interval_minutes": 120})


# --- the variations switchboard -------------------------------------------------
#
# Turning a variation off in the control room is meant to remove it from the
# site *and* stop it being accepted. These tests pin both halves, plus the
# refusal to end up with nothing in play at all.


def test_state_reports_which_variations_are_in_play(as_admin, client):
    as_admin.patch("/api/admin/settings", json={"variations": [1, 4]}, headers=ORIGIN)
    assert client.get("/api/state").json()["variations"] == [1, 4]
    store.update_settings({"variations": [1, 2]})


def test_variations_are_normalised(as_admin):
    """Duplicates and out-of-order input still land as a sorted set."""
    response = as_admin.patch(
        "/api/admin/settings", json={"variations": [4, 1, 1]}, headers=ORIGIN
    )
    assert response.status_code == 200
    assert response.json()["settings"]["variations"] == [1, 4]
    store.update_settings({"variations": [1, 2]})


@pytest.mark.parametrize("value", [[], [5], ["1"], "1", [0]])
def test_an_unusable_variation_list_is_refused(as_admin, value):
    """The whole site is drawn from this list, so it must never go empty or junk."""
    before = store.get_settings()["variations"]
    response = as_admin.patch("/api/admin/settings", json={"variations": value}, headers=ORIGIN)
    assert response.status_code == 400
    assert store.get_settings()["variations"] == before


def test_a_switched_off_variation_refuses_uploads(as_user):
    """The submit form stops offering it; the API has to stop taking it too."""
    store.update_settings({"variations": [1]})
    try:
        response = as_user.post(
            "/api/submit",
            files={"file": ("ME24B152_4.py", b"class Bot:\n    pass\n")},
            headers=ORIGIN,
        )
        assert response.status_code == 400
        assert "not in play" in response.json()["detail"]
    finally:
        store.update_settings({"variations": [1, 2]})


# --- cross-origin --------------------------------------------------------------


def test_cross_origin_state_change_is_rejected(as_admin):
    response = as_admin.patch(
        "/api/admin/settings",
        json={"interval_minutes": 5},
        headers={"Origin": "https://evil.example"},
    )
    assert response.status_code == 403
    assert store.get_settings()["interval_minutes"] != 5


# --- the hidden bounds are the one setting that can break every game ------------


class TestBlockBoundsValidation:
    """`block_bounds` is typed into the console minutes before a run.

    M_b divides the normalised profit and scales every capital draw, so a zero,
    a negative or an inverted pair does not degrade the showdown — it takes the
    whole thing down. It used to be stored with no checks at all.
    """

    def _patch(self, as_admin, bounds):
        return as_admin.patch(
            "/api/admin/settings", json={"block_bounds": bounds}, headers=ORIGIN
        )

    def test_flat_schedule_is_accepted_and_nested(self, as_admin):
        response = self._patch(as_admin, [[0, 100], [40, 60], [0, 400], [5, 25]])
        assert response.status_code == 200
        assert response.json()["settings"]["block_bounds"] == [
            [[0.0, 100.0], [40.0, 60.0], [0.0, 400.0], [5.0, 25.0]]
        ]

    def test_per_iteration_schedules_are_accepted(self, as_admin):
        bounds = [[[0, 100], [40, 60]], [[10, 30], [0, 250]]]
        response = self._patch(as_admin, bounds)
        assert response.status_code == 200
        assert len(response.json()["settings"]["block_bounds"]) == 2

    @pytest.mark.parametrize(
        "bad",
        [
            [],
            [[100, 0]],
            [[5, 5]],
            [[-50, -10]],
            [["a", "b"]],
            [[0, 100, 7]],
            "not a list",
        ],
    )
    def test_bad_bounds_are_refused_with_a_readable_message(self, as_admin, bad):
        response = self._patch(as_admin, bad)
        assert response.status_code == 400
        assert response.json()["detail"]

    def test_a_refused_patch_does_not_change_the_stored_bounds(self, as_admin):
        good = [[0, 100], [40, 60], [0, 400], [5, 25]]
        self._patch(as_admin, good)
        before = store.get_settings()["block_bounds"]
        assert self._patch(as_admin, [[9, 1]]).status_code == 400
        assert store.get_settings()["block_bounds"] == before

    def test_bounds_never_reach_the_browser(self, client, as_admin):
        """They are the answer to the whole problem, so `/api/state` withholds
        them (`store.SECRET_SETTING_KEYS`)."""
        before = store.get_settings()["block_bounds"]
        try:
            self._patch(as_admin, [[0, 137.5], [40, 60], [0, 400], [5, 25]])
            assert "137.5" not in client.get("/api/state").text
        finally:
            store.update_settings({"block_bounds": before})
