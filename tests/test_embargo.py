"""Nothing about an unreleased variation may reach a participant.

Variations 3 and 4 are released after mock auction 1. Between the orientation
session and that moment there are exactly two things a participant can get hold
of — the starter kit zip, and whatever the browser is served — so both are
checked here. These are cheap tests guarding an irreversible mistake: once the
V4 rules have been downloaded, they cannot be un-downloaded.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

import pytest

import build_kit
from server import store
from server.app import app

try:
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover - fastapi is a hard dependency
    TestClient = None


@pytest.fixture
def client():
    """A test client whose settings changes are rolled back afterwards.

    These tests flip `variations` around, which is a stored setting — leaving it
    on [1, 2, 3, 4] would quietly change what every later test sees.
    """
    before = store.get_settings().get("variations")
    with TestClient(app) as test_client:
        yield test_client
    store.update_settings({"variations": before})

REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = REPO_ROOT / "web"
KIT_ZIP = REPO_ROOT / "public" / "starter-kit.zip"

#: Phrases that give away a variation that has not been released. Deliberately
#: about the *rules*, not the bare digits 3 and 4 — "variation 3" appears in
#: perfectly innocent copy like "variations 3 and 4 open later".
GIVEAWAYS = (
    "runner-up penalty",
    "funded second price",
    "top_bids_last_round",
    "payoff_v3",
    "payoff_v4",
    "second-highest bidder pays",
    "zero-sum",
    "0.5, 0.3 and 0.2",
    "ranks 3-5",
    "ranks 3–5",
)


# --- the starter kit ------------------------------------------------------------


def test_kit_contains_only_allowed_files():
    """The kit is Template + README + runner + samples, and nothing else.

    It used to ship a full copy of `src/auction/`, which handed over the
    tie-break tolerance, the elimination rule, the group size and both
    unreleased variations.
    """
    with zipfile.ZipFile(KIT_ZIP) as archive:
        names = {n.split("/", 1)[1] for n in archive.namelist()}
    assert names == set(build_kit.ALLOWED), (
        "starter-kit.zip does not match build_kit.ALLOWED — "
        "rerun `python build_kit.py` and commit the zip"
    )


def test_kit_ships_no_engine_source():
    with zipfile.ZipFile(KIT_ZIP) as archive:
        names = archive.namelist()
    for forbidden in ("src/auction", "auction_reference", "engine.py", "variations.py"):
        assert not any(forbidden in n for n in names), f"kit ships {forbidden}"


def test_kit_says_nothing_about_unreleased_variations():
    with zipfile.ZipFile(KIT_ZIP) as archive:
        blob = b"\n".join(archive.read(n) for n in archive.namelist()).decode("utf-8")
    lowered = blob.lower()
    for phrase in GIVEAWAYS:
        assert phrase not in lowered, f"starter kit leaks {phrase!r}"


def test_build_kit_refuses_unexpected_files(tmp_path, monkeypatch):
    """An engine file dropped into `starter-kit/` must fail the build, loudly."""
    stray = build_kit.KIT_DIR / "_stray_test_file.py"
    stray.write_text("# left here by accident\n", encoding="utf-8")
    try:
        with pytest.raises(SystemExit, match="unexpected files"):
            build_kit.collect()
    finally:
        stray.unlink()


def test_build_kit_refuses_embargoed_content():
    """`build` blocks a kit that mentions a variation still under embargo."""
    files = build_kit.collect()
    assert build_kit.check_embargo(files) == [], "kit already mentions V3/V4"

    template = build_kit.KIT_DIR / "Template.py"
    original = template.read_text(encoding="utf-8")
    try:
        template.write_text(original + "\n# see variation 4 for the penalty\n", encoding="utf-8")
        with pytest.raises(SystemExit, match="unreleased variation"):
            build_kit.build()
    finally:
        template.write_text(original, encoding="utf-8")


# --- what the browser is served -------------------------------------------------


def _served_files() -> list[Path]:
    """Everything nginx hands out as a static asset (`deploy/nginx.conf`)."""
    files = [REPO_ROOT / "index.html"]
    files += [p for p in WEB_DIR.rglob("*") if p.is_file() and p.suffix in {".js", ".html", ".css"}]
    return files


def test_served_bundle_says_nothing_about_unreleased_variations():
    """The V3/V4 rules must not sit in the JS bundle waiting to be read.

    `enabledVariations()` only filters them at render time, which is no defence
    at all against devtools. The copy lives in `server/late_variations.js`,
    served by `/api/variations/late.js`, which 404s until release.
    """
    offenders = []
    for path in _served_files():
        lowered = path.read_text(encoding="utf-8", errors="replace").lower()
        for phrase in GIVEAWAYS:
            if phrase in lowered:
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {phrase!r}")
    assert not offenders, "served assets leak unreleased variations:\n  " + "\n  ".join(offenders)


def test_late_variations_module_is_not_under_web():
    assert not (WEB_DIR / "late_variations.js").exists()
    assert (REPO_ROOT / "server" / "late_variations.js").is_file()


def test_nginx_blocks_the_server_directory():
    """`late_variations.js` is only safe under `server/` if nginx refuses it."""
    conf = (REPO_ROOT / "deploy" / "nginx-app.conf").read_text(encoding="utf-8")
    blocked = re.search(r"location ~ \^/\(\?:([^)]+)\)", conf)
    assert blocked, "could not find the deny-list location block in nginx-app.conf"
    assert "server" in blocked.group(1).split("|")


# --- the API gate ---------------------------------------------------------------


def test_late_js_is_404_until_a_late_variation_is_enabled(client):
    store.update_settings({"variations": [1, 2]})
    assert client.get("/api/variations/late.js").status_code == 404


@pytest.mark.parametrize("variations", ([1, 2, 3], [1, 2, 4], [1, 2, 3, 4]))
def test_late_js_is_served_once_released(client, variations):
    store.update_settings({"variations": variations})
    response = client.get("/api/variations/late.js")
    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]
    assert "Runner-up Penalty" in response.text
    assert response.headers.get("cache-control") == "no-store"


def test_late_js_closes_again_if_a_variation_is_withdrawn(client):
    store.update_settings({"variations": [1, 2, 3]})
    assert client.get("/api/variations/late.js").status_code == 200
    store.update_settings({"variations": [1, 2]})
    assert client.get("/api/variations/late.js").status_code == 404


def test_public_state_does_not_name_unreleased_variations(client):
    store.update_settings({"variations": [1, 2]})
    body = client.get("/api/state").text.lower()
    for phrase in GIVEAWAYS:
        assert phrase not in body
