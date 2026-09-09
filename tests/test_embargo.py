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


def test_committed_zip_is_what_a_fresh_build_produces(tmp_path):
    """The shipped archive must be the current sources, not last week's.

    `test_kit_contains_only_allowed_files` only compares NAMES, so editing
    `Template.py` and forgetting `python build_kit.py` shipped a stale kit with
    every test still green. Compare the bytes of each member instead — the zip's
    own container bytes differ run to run (timestamps), so they are not
    comparable, but its contents are.
    """
    fresh = build_kit.build(output=tmp_path / "fresh.zip")
    with zipfile.ZipFile(fresh) as built, zipfile.ZipFile(KIT_ZIP) as shipped:
        assert sorted(built.namelist()) == sorted(shipped.namelist())
        stale = [
            name for name in built.namelist()
            if built.read(name) != shipped.read(name)
        ]
    assert not stale, (
        "public/starter-kit.zip is out of date for: " + ", ".join(stale) +
        "\n  rerun `python build_kit.py` and commit the zip"
    )


def test_late_kit_is_staged_outside_the_shipped_directory():
    """The V3/V4 material must not live under `starter-kit/` before release.

    Everything in that directory is one careless `ALLOWED` edit from being
    published. Staging elsewhere is what makes the pre-release kit safe by
    construction rather than by vigilance.
    """
    assert build_kit.LATE_DIR.is_dir(), "late-kit/ is missing"
    for name in build_kit.LATE_ALLOWED:
        assert (build_kit.LATE_DIR / name).is_file(), f"late-kit/{name} is missing"
    # `local_test.py` maps onto itself on purpose — the four-variation runner
    # replaces the two-variation one. Everything else must be genuinely new.
    added = set(build_kit.LATE_ALLOWED.values()) - {"local_test.py"}
    assert not (added & set(build_kit.ALLOWED)), (
        "late-kit files already ship in the pre-release kit: "
        + ", ".join(sorted(added & set(build_kit.ALLOWED)))
    )


def test_nginx_blocks_the_late_kit_directory():
    conf = (REPO_ROOT / "deploy" / "nginx-app.conf").read_text(encoding="utf-8")
    blocked = re.search(r"location ~ \^/\(\?:([^)]+)\)", conf)
    assert blocked, "could not find the deny-list location block in nginx-app.conf"
    assert "late-kit" in blocked.group(1).split("|")


def test_prerelease_build_ships_nothing_from_the_late_kit(tmp_path):
    """Belt and braces over the embargo grep: the late files must be absent."""
    archive_path = build_kit.build(output=tmp_path / "prerelease.zip")
    with zipfile.ZipFile(archive_path) as archive:
        names = {n.split("/", 1)[1] for n in archive.namelist()}
    assert names == set(build_kit.ALLOWED)
    assert "Template_3.py" not in names
    assert "Template_4.py" not in names
    assert "README_v3_v4.md" not in names


def test_release_build_adds_the_late_variations(tmp_path):
    """`--release-v3-v4` is the switch that publishes them, and it must work."""
    archive_path = build_kit.build(released=True, output=tmp_path / "released.zip")
    with zipfile.ZipFile(archive_path) as archive:
        names = {n.split("/", 1)[1] for n in archive.namelist()}
        readme = archive.read("trading-bot-starter-kit/README.md").decode("utf-8")
        runner = archive.read("trading-bot-starter-kit/local_test.py").decode("utf-8")

    assert names == set(build_kit.ALLOWED) | set(build_kit.LATE_ALLOWED.values())
    assert build_kit.EMBARGO_NOTICE not in readme, "the released kit still says V1/V2 only"
    assert build_kit.RELEASED_NOTICE in readme
    # The four-variation runner replaces the two-variation one, same filename.
    assert "choices=(1, 2, 3, 4)" in runner


def test_release_readme_swap_fails_loudly_if_the_notice_is_reworded(tmp_path):
    """Silently shipping a kit that says 'variations 1 and 2 only' next to a
    `Template_4.py` is worse than failing the build."""
    readme = build_kit.KIT_DIR / "README.md"
    original = readme.read_text(encoding="utf-8")
    try:
        readme.write_text(original.replace(build_kit.EMBARGO_NOTICE, "> reworded"),
                          encoding="utf-8")
        with pytest.raises(SystemExit, match="embargo notice"):
            build_kit.build(released=True, output=tmp_path / "x.zip")
    finally:
        readme.write_text(original, encoding="utf-8")


def test_build_kit_refuses_unexpected_files(tmp_path, monkeypatch):
    """An engine file dropped into `starter-kit/` must fail the build, loudly."""
    stray = build_kit.KIT_DIR / "_stray_test_file.py"
    stray.write_text("# left here by accident\n", encoding="utf-8")
    try:
        with pytest.raises(SystemExit, match="unexpected files"):
            build_kit.collect()
    finally:
        stray.unlink()


def test_build_kit_refuses_unexpected_late_kit_files():
    """`late-kit/` is audited on every build, released or not — a stray engine
    file there is a leak waiting for someone to flip the release switch."""
    stray = build_kit.LATE_DIR / "_stray_test_file.py"
    stray.write_text("# left here by accident\n", encoding="utf-8")
    try:
        with pytest.raises(SystemExit, match="unexpected files under late-kit"):
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


# --- the scoring document -------------------------------------------------------

SCORING_PUBLIC = REPO_ROOT / "docs" / "scoring-public.pdf"
SCORING_FULL = REPO_ROOT / "docs" / "scoring.pdf"


def _pdf_text(path: Path) -> str:
    """The PDF's text, lowercased. Skips the test if poppler is not installed."""
    import shutil
    import subprocess

    if shutil.which("pdftotext") is None:
        pytest.skip("pdftotext (poppler) is not installed")
    out = subprocess.run(
        ["pdftotext", str(path), "-"], capture_output=True, text=True, check=True
    )
    return out.stdout.lower()


def test_both_scoring_pdfs_are_committed():
    """The VM has no TeX install, so the API serves these out of the checkout."""
    assert SCORING_PUBLIC.is_file(), "run ./scripts/build_docs.sh and commit the PDFs"
    assert SCORING_FULL.is_file(), "run ./scripts/build_docs.sh and commit the PDFs"


def test_the_public_scoring_pdf_says_nothing_about_unreleased_variations():
    """This is the one that goes out before mock auction 1."""
    text = _pdf_text(SCORING_PUBLIC)
    for phrase in GIVEAWAYS:
        assert phrase not in text, f"scoring-public.pdf leaks {phrase!r}"


def test_the_full_scoring_pdf_actually_describes_them():
    """Otherwise the `\\ifreleased` guards are wrong in the other direction and
    the released document is silently missing half its subject."""
    text = _pdf_text(SCORING_FULL)
    assert "runner-up penalty" in text
    assert "funded second price" in text


def test_the_scoring_pdf_is_gated_the_same_way_late_js_is(client):
    """It carries the V3 and V4 payoff rules, so before release the full
    document must not be reachable — the public variant is served instead."""
    store.update_settings({"variations": [1, 2]})
    before = client.get("/api/docs/scoring.pdf")
    assert before.status_code == 200
    assert before.headers["content-type"] == "application/pdf"

    store.update_settings({"variations": [1, 2, 3]})
    after = client.get("/api/docs/scoring.pdf")
    assert after.status_code == 200
    assert len(after.content) != len(before.content), (
        "the same PDF is served before and after release — the gate does nothing"
    )
    assert after.content == SCORING_FULL.read_bytes()
    assert before.content == SCORING_PUBLIC.read_bytes()


def test_the_scoring_pdfs_are_not_served_as_static_files():
    """They live under `docs/`, which nginx blocks. A copy under `public/` would
    be one filename guess away from defeating the gate entirely."""
    assert not (REPO_ROOT / "public" / "scoring.pdf").exists()
    assert not (REPO_ROOT / "web" / "scoring.pdf").exists()
    conf = (REPO_ROOT / "deploy" / "nginx-app.conf").read_text(encoding="utf-8")
    blocked = re.search(r"location ~ \^/\(\?:([^)]+)\)", conf)
    assert "docs" in blocked.group(1).split("|")


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
