"""The variation 3 and 4 material staged in `late-kit/`.

These files ship to participants the moment mock auction 1 finishes, and from
then on they are the *only* description of V3 and V4 most people will read. A
runner that settles a round differently from the engine is worse than no runner
at all: it teaches a wrong lesson, confidently, for four days.

So the runner's payoff rules are checked against `src.auction.variations`
directly rather than eyeballed, and the templates are checked to be things the
submission pipeline would actually accept.
"""

from __future__ import annotations

import ast
import importlib.util
import random
from pathlib import Path

import pytest

import build_kit
from harness.validate import parse_filename
from sandbox.policy import check_source
from src.auction import variations as V

LATE_DIR = build_kit.LATE_DIR
TEMPLATES = ("Template_3.py", "Template_4.py")


@pytest.fixture(scope="module")
def runner():
    """`late-kit/local_test.py`, imported as a module."""
    path = LATE_DIR / "local_test.py"
    spec = importlib.util.spec_from_file_location("late_local_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- the runner settles rounds the way the engine does --------------------------


def _engine_ranked(variation, values, bids, max_value, shuffle_seed):
    """What `src.auction.engine` would pay, given the same tie-break shuffle."""
    order = list(range(len(bids)))
    random.Random(shuffle_seed).shuffle(order)
    order.sort(key=lambda i: -bids[i])

    payoffs = [0.0] * len(bids)
    if variation == 3:
        top = bids[order[0]]
        payoffs[order[0]] = V.payoff_v3_winner(max_value, top)
        if len(order) > 1:
            payoffs[order[1]] = V.payoff_v3_second(max_value, top)
    else:
        by_rank = V.payoff_v4(max_value, [bids[i] for i in order])
        for position, index in enumerate(order):
            payoffs[index] = by_rank[position]
    return payoffs


@pytest.mark.parametrize("variation", (3, 4))
def test_ranked_settlement_matches_the_engine(runner, variation):
    """Randomised, across group sizes and the b1 > X branch."""
    rng = random.Random(20260912)
    for trial in range(3000):
        n = rng.choice([2, 3, 4, 5, 6, 8, 20])
        # Bids range above the values so the V4 `b1 > X` branch is exercised.
        bids = [round(rng.uniform(0.0, 120.0), 2) for _ in range(n)]
        values = [round(rng.uniform(0.0, 100.0), 2) for _ in range(n)]
        max_value = max(values)

        got, ranks = runner.settle_ranked(
            variation, values, bids, max_value, random.Random(trial)
        )
        expected = _engine_ranked(variation, values, bids, max_value, trial)

        assert got == pytest.approx(expected, abs=1e-9), (
            f"V{variation} n={n} bids={bids} X={max_value}"
        )
        assert sorted(ranks) == list(range(1, n + 1)), "ranks must be a permutation"


@pytest.mark.parametrize("variation", (1, 2))
def test_first_price_settlement_matches_the_engine(runner, variation):
    """Coarse bids, so genuine ties happen and the all-tied-win rule is tested."""
    rng = random.Random(7)
    for _ in range(3000):
        n = rng.choice([2, 3, 4, 6])
        bids = [round(rng.uniform(0.0, 20.0), 1) for _ in range(n)]
        values = [round(rng.uniform(0.0, 100.0), 2) for _ in range(n)]
        max_value = max(values)

        got, ranks = runner.settle_first_price(variation, values, bids, max_value)

        top = max(bids)
        expected = [
            (V.payoff_v1(values[i], top) if variation == 1 else V.payoff_v2(max_value, top))
            if abs(b - top) <= V_TIE
            else 0.0
            for i, b in enumerate(bids)
        ]
        assert got == pytest.approx(expected, abs=1e-9), f"V{variation} bids={bids}"
        assert all(ranks[i] == 1 for i, b in enumerate(bids) if abs(b - top) <= V_TIE)


V_TIE = 1e-9


def test_v4_is_zero_sum_when_the_winner_did_not_overpay(runner):
    """The property the variation is built on, checked on the runner itself."""
    rng = random.Random(4)
    for trial in range(2000):
        n = rng.choice([5, 6, 8, 20])
        values = [round(rng.uniform(0.0, 100.0), 2) for _ in range(n)]
        max_value = max(values)
        # Keep every bid under X so the zero-sum branch is the one taken.
        bids = [round(rng.uniform(0.0, max_value), 2) for _ in range(n)]

        payoffs, _ = runner.settle_ranked(4, values, bids, max_value, random.Random(trial))
        assert sum(payoffs) == pytest.approx(0.0, abs=1e-9), f"bids={bids} X={max_value}"


# --- the templates are submittable ---------------------------------------------


@pytest.mark.parametrize("name", TEMPLATES)
def test_template_defines_the_bot_contract(name):
    tree = ast.parse((LATE_DIR / name).read_text(encoding="utf-8"))
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef)]
    assert [c.name for c in classes] == ["Bot"], f"{name} must define exactly one class, `Bot`"
    methods = {n.name for n in classes[0].body if isinstance(n, ast.FunctionDef)}
    assert {"__init__", "get_bid"} <= methods


@pytest.mark.parametrize("name", TEMPLATES)
def test_template_passes_the_upload_policy(name):
    """A template a participant cannot submit unmodified is a broken template."""
    source = (LATE_DIR / name).read_text(encoding="utf-8")
    assert check_source(source) == [], f"{name} is rejected by sandbox.policy"


@pytest.mark.parametrize("name,variation", (("Template_3.py", 3), ("Template_4.py", 4)))
def test_template_filename_convention_is_the_one_the_site_accepts(name, variation):
    """`Template_3.py` -> copy to `ME24B152_3.py`, which must parse as V3."""
    assert parse_filename(f"ME24B152_{variation}.py") == ("ME24B152", variation)
    assert name.endswith(f"_{variation}.py")


@pytest.mark.parametrize("name,forbidden", (
    ("Template_3.py", "top_bids_last_round"),
))
def test_template_3_does_not_promise_an_observation_it_never_gets(name, forbidden):
    """`top_bids_last_round` is variation 4 only — the engine does not put it in
    a V3 observation, so a V3 template touching it would KeyError on round 2."""
    assert forbidden not in (LATE_DIR / name).read_text(encoding="utf-8")
