"""Build the participant starter kit into ``public/starter-kit.zip``.

    python build_kit.py

Run this after changing anything under ``starter-kit/`` and commit the resulting
zip — the VM serves files straight out of the repo and has no build step, so the
archive has to be in git.

WHAT THE KIT MAY CONTAIN
========================
Only the four things below. In particular the kit does **not** ship
``src/auction/`` or any copy of it. The engine source gives away the exact
tie-break tolerance, the elimination rule, the group size, the number of
iterations, and — before they are released — the whole of variations 3 and 4.
Participants get the published rules and a black-box local runner; that is all
they are entitled to and all they need.

``ALLOWED`` is enforced, not documented: ``build`` refuses to run if anything
else has appeared under ``starter-kit/``.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
KIT_DIR = REPO_ROOT / "starter-kit"
OUTPUT = REPO_ROOT / "public" / "starter-kit.zip"

#: Every file the kit is allowed to contain, relative to ``starter-kit/``.
ALLOWED = (
    "Template.py",
    "README.md",
    "local_test.py",
    "sample_bots/sample_bot_1.py",
    "sample_bots/sample_bot_2.py",
    "sample_bots/sample_bot_3.py",
)

#: Words that must not appear anywhere in the kit before variations 3 and 4 are
#: released. Checked literally — the point is to catch a careless paste, not to
#: be clever about it.
EMBARGOED = (
    "variation 3",
    "variation 4",
    "variation_3",
    "variation_4",
    "runner-up penalty",
    "V3_PENALTY",
    "V4_PENALTY",
    "payoff_v3",
    "payoff_v4",
)


def collect() -> list[Path]:
    """The kit's files, after checking nothing unexpected is in the directory."""
    on_disk = {
        p.relative_to(KIT_DIR).as_posix()
        for p in KIT_DIR.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    }
    unexpected = sorted(on_disk - set(ALLOWED))
    if unexpected:
        raise SystemExit(
            "refusing to build: unexpected files under starter-kit/\n  "
            + "\n  ".join(unexpected)
            + "\n\nThe kit is a published artefact. Add the file to ALLOWED in\n"
            "build_kit.py only if participants are genuinely meant to have it."
        )

    missing = [name for name in ALLOWED if not (KIT_DIR / name).is_file()]
    if missing:
        raise SystemExit("refusing to build: missing " + ", ".join(missing))

    return [KIT_DIR / name for name in ALLOWED]


def check_embargo(files: list[Path]) -> list[str]:
    """Flag any mention of an unreleased variation. Returns the complaints."""
    problems = []
    for path in files:
        text = path.read_text(encoding="utf-8").lower()
        for phrase in EMBARGOED:
            if phrase.lower() in text:
                problems.append(f"{path.name}: mentions {phrase!r}")
    return problems


def build(*, allow_embargoed: bool = False) -> Path:
    files = collect()

    problems = check_embargo(files)
    if problems and not allow_embargoed:
        raise SystemExit(
            "refusing to build: the kit mentions an unreleased variation\n  "
            + "\n  ".join(problems)
            + "\n\nPass --release-v3-v4 once they are actually released."
        )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUTPUT, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            relative = path.relative_to(KIT_DIR).as_posix()
            archive.write(path, f"trading-bot-starter-kit/{relative}")
    return OUTPUT


if __name__ == "__main__":
    output = build(allow_embargoed="--release-v3-v4" in sys.argv)
    size_kb = output.stat().st_size / 1024
    with zipfile.ZipFile(output) as archive:
        names = archive.namelist()
    print(f"  built {output.relative_to(REPO_ROOT)} — {len(names)} files, {size_kb:.1f} KB")
    for name in names:
        print(f"    {name}")
