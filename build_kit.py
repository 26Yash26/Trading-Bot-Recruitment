"""Build the participant starter kit into ``public/starter-kit.zip``.

    python build_kit.py                    # variations 1 and 2 (pre-release)
    python build_kit.py --release-v3-v4    # all four (after mock auction 1)

Run this after changing anything under ``starter-kit/`` or ``late-kit/`` and
commit the resulting zip — the VM serves files straight out of the repo and has
no build step, so the archive has to be in git.

TWO KITS, ONE FILENAME
======================
The kit ships under a fixed URL that changes meaning mid-event, which is why
nginx serves ``/public/`` with ``no-cache``. Before mock auction 1 the archive
holds variations 1 and 2 and says nothing whatsoever about 3 and 4. After it,
``--release-v3-v4`` adds ``Template_3.py``, ``Template_4.py`` and their README
supplement, and swaps ``local_test.py`` for the four-variation runner.

The V3/V4 material is staged in ``late-kit/``, not ``starter-kit/``, for exactly
the reason ``server/late_variations.js`` is not under ``web/``: a file that is
not in the shipped set cannot leak from it. ``late-kit/`` is unreachable over
HTTP — nginx resolves no path outside ``/web/`` and ``/public/`` — and it is on
the deny-list as well.

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
LATE_DIR = REPO_ROOT / "late-kit"
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

#: What ``--release-v3-v4`` adds, as ``late-kit/`` name -> name inside the kit.
#: ``local_test.py`` maps onto itself deliberately: the four-variation runner
#: REPLACES the two-variation one rather than sitting beside it, so a
#: participant who re-downloads has one runner and one command to remember.
LATE_ALLOWED = {
    "Template_3.py": "Template_3.py",
    "Template_4.py": "Template_4.py",
    "README_v3_v4.md": "README_v3_v4.md",
    "local_test.py": "local_test.py",
}

#: The embargo notice in ``starter-kit/README.md``, and what replaces it once
#: the variations are out. Matched literally: if the README is reworded the
#: build fails loudly rather than shipping a kit that contradicts itself.
EMBARGO_NOTICE = """> **Variations 1 and 2 only.** Variations 3 and 4 are released after mock
> auction 1. Nothing about them is in this kit, and the site will not accept a
> `_3.py` or `_4.py` file until they open."""

RELEASED_NOTICE = """> **All four variations are open.** Variations 1 and 2 are described below.
> Variations 3 and 4 have their own templates and their own supplement,
> `README_v3_v4.md` — read that one too."""

#: The file tree at the top of the kit README, and what it becomes on release.
#: A tree that does not list the files in the archive is worse than no tree.
EMBARGO_TREE = """```
starter-kit/
├── Template.py       ← copy this, edit this, submit this
├── local_test.py     a rough local runner, so you can check it works
├── sample_bots/      the three bots from the problem statement
└── README.md         this file
```"""

RELEASED_TREE = """```
starter-kit/
├── Template.py        ← variations 1 and 2
├── Template_3.py      ← variation 3
├── Template_4.py      ← variation 4
├── local_test.py      a rough local runner, so you can check it works
├── sample_bots/       the three bots from the problem statement
├── README.md          this file
└── README_v3_v4.md    variations 3 and 4: rules, observations, testing
```"""

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


def _audit(directory: Path, expected, label: str) -> None:
    """Fail unless ``directory`` holds exactly ``expected`` and nothing else."""
    on_disk = {
        p.relative_to(directory).as_posix()
        for p in directory.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    }
    unexpected = sorted(on_disk - set(expected))
    if unexpected:
        raise SystemExit(
            f"refusing to build: unexpected files under {label}/\n  "
            + "\n  ".join(unexpected)
            + "\n\nThe kit is a published artefact. Add the file to the allowlist in\n"
            "build_kit.py only if participants are genuinely meant to have it."
        )

    missing = [name for name in expected if not (directory / name).is_file()]
    if missing:
        raise SystemExit(f"refusing to build: {label}/ is missing " + ", ".join(missing))


def collect(*, released: bool = False) -> dict[str, Path]:
    """The kit's contents as ``name inside the kit`` -> source path.

    Both source directories are audited every time, released or not: a stray
    engine file under ``late-kit/`` is just as much a leak waiting to happen as
    one under ``starter-kit/``, and it should not take a release to notice it.
    """
    _audit(KIT_DIR, ALLOWED, "starter-kit")
    _audit(LATE_DIR, LATE_ALLOWED, "late-kit")

    files = {name: KIT_DIR / name for name in ALLOWED}
    if released:
        files.update({dst: LATE_DIR / src for src, dst in LATE_ALLOWED.items()})
    return files


def check_embargo(files) -> list[str]:
    """Flag any mention of an unreleased variation. Returns the complaints."""
    paths = files.values() if isinstance(files, dict) else files
    problems = []
    for path in paths:
        text = path.read_text(encoding="utf-8").lower()
        for phrase in EMBARGOED:
            if phrase.lower() in text:
                problems.append(f"{path.name}: mentions {phrase!r}")
    return problems


#: ``(what to find, what to replace it with, what to call it)`` on release.
RELEASE_EDITS = (
    (EMBARGO_NOTICE, RELEASED_NOTICE, "embargo notice"),
    (EMBARGO_TREE, RELEASED_TREE, "file tree"),
)


def readme_text(source: Path, *, released: bool) -> str:
    """``README.md``, rewritten for the released kit.

    Two passes, both matched literally. Failing loudly beats shipping a kit whose
    own README says "variations 1 and 2 only" next to a ``Template_4.py``, or
    whose file tree does not list half the archive.
    """
    text = source.read_text(encoding="utf-8")
    if not released:
        return text
    for find, replace, label in RELEASE_EDITS:
        if find not in text:
            raise SystemExit(
                f"refusing to build: starter-kit/README.md no longer contains the\n"
                f"{label} build_kit.py knows how to replace. Update the matching\n"
                "constant in build_kit.py to the current wording."
            )
        text = text.replace(find, replace)
    return text


def build(*, released: bool = False, output: Path | None = None) -> Path:
    """Write the kit archive and return its path.

    ``output`` is for tests, which must be able to build both kits without
    touching the committed ``public/starter-kit.zip``.
    """
    output = OUTPUT if output is None else Path(output)
    files = collect(released=released)

    if not released:
        problems = check_embargo(files)
        if problems:
            raise SystemExit(
                "refusing to build: the kit mentions an unreleased variation\n  "
                + "\n  ".join(problems)
                + "\n\nPass --release-v3-v4 once they are actually released."
            )

    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, path in files.items():
            if name == "README.md":
                # Text, not a file copy: the notice at the top of the README is
                # the one thing that has to change between the two kits.
                archive.writestr(
                    f"trading-bot-starter-kit/{name}",
                    readme_text(path, released=released),
                )
            else:
                archive.write(path, f"trading-bot-starter-kit/{name}")
    return output


if __name__ == "__main__":
    released = "--release-v3-v4" in sys.argv
    output = build(released=released)
    size_kb = output.stat().st_size / 1024
    with zipfile.ZipFile(output) as archive:
        names = archive.namelist()
    which = "all four variations" if released else "variations 1 and 2"
    print(f"  built {output.relative_to(REPO_ROOT)} — {which}")
    print(f"  {len(names)} files, {size_kb:.1f} KB")
    for name in names:
        print(f"    {name}")
