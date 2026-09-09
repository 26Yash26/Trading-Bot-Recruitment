"""Per-block uniform sampling, and the per-iteration schedules built on it."""

from pathlib import Path

import numpy as np
import pytest

from harness.evaluate import ShowdownSettings, build_jobs
from harness.simulate import BotSpec
from src.auction.distributions import ValueSampler, normalise_block_bounds

SAMPLE_BOT = (
    Path(__file__).resolve().parent.parent / "starter-kit" / "sample_bots" / "sample_bot_1.py"
)


def test_values_fall_within_block_bounds():
    s = ValueSampler([(10.0, 20.0), (100.0, 200.0)], seed=1, block_size=500)
    v0 = s.draw(0, 50)
    assert np.all(v0 >= 10.0) and np.all(v0 <= 20.0)
    v1 = s.draw(500, 50)
    assert np.all(v1 >= 100.0) and np.all(v1 <= 200.0)


def test_bounds_switch_every_block_size_rounds():
    s = ValueSampler([(0.0, 1.0), (1.0, 2.0), (2.0, 3.0), (3.0, 4.0)], seed=1, block_size=500)
    assert s.bounds_for_round(0) == (0.0, 1.0)
    assert s.bounds_for_round(499) == (0.0, 1.0)
    assert s.bounds_for_round(500) == (1.0, 2.0)
    assert s.bounds_for_round(1999) == (3.0, 4.0)


def test_last_block_bounds_reused_beyond_supplied_blocks():
    s = ValueSampler([(0.0, 1.0), (1.0, 2.0)], seed=1, block_size=500)
    assert s.bounds_for_round(5000) == (1.0, 2.0)


def test_same_seed_same_draws():
    a = ValueSampler([(0.0, 100.0)], seed=42)
    b = ValueSampler([(0.0, 100.0)], seed=42)
    assert np.array_equal(a.draw(0, 20), b.draw(0, 20))


def test_different_seed_different_draws():
    a = ValueSampler([(0.0, 100.0)], seed=1)
    b = ValueSampler([(0.0, 100.0)], seed=2)
    assert not np.array_equal(a.draw(0, 20), b.draw(0, 20))


def test_rejects_inverted_bounds():
    with pytest.raises(ValueError):
        ValueSampler([(100.0, 0.0)], seed=1)


# --- block bounds, one schedule per iteration ----------------------------------


class TestNormaliseBlockBounds:
    """`normalise_block_bounds` is what the admin console types into.

    It guards the one setting that can take down every game at once: M_b is the
    divisor in the normalised profit and the scale of the capital draw, so a
    zero, a negative or an inverted pair breaks the whole showdown.
    """

    def test_flat_schedule_is_wrapped(self):
        assert normalise_block_bounds([(0, 100), (25, 75)]) == [
            [(0.0, 100.0), (25.0, 75.0)]
        ]

    def test_per_iteration_schedules_are_kept_apart(self):
        out = normalise_block_bounds([[(0, 10), (5, 50)], [(1, 2), (3, 4)]])
        assert out == [[(0.0, 10.0), (5.0, 50.0)], [(1.0, 2.0), (3.0, 4.0)]]

    def test_block_count_is_checked_when_asked(self):
        with pytest.raises(ValueError, match="expected 4 blocks"):
            normalise_block_bounds([(0, 100), (0, 50)], num_blocks=4)

    @pytest.mark.parametrize(
        "bad, message",
        [
            ([], "non-empty"),
            ([(5, 5)], "greater than"),
            ([(10, 4)], "greater than"),
            ([(-20, -5)], "must be positive"),
            ([("a", "b")], "must be numbers"),
            ([(0, 100, 7)], r"\[min, max\] pair"),
            ([(0, float("inf"))], "finite"),
        ],
    )
    def test_bad_input_is_refused(self, bad, message):
        with pytest.raises(ValueError, match=message):
            normalise_block_bounds(bad)


class TestBoundsPerIteration:
    """Problem statement §9 wants iteration 2 to face *different distributions*,
    not the same ones under a fresh seed.

    `bounds_mode="random"` gets that for free — every iteration draws its own
    blocks off the grids. These tests cover the other mode, `"fixed"`, where an
    admin supplies the schedules by hand to reproduce a specific run.
    """

    def test_each_iteration_gets_its_own_schedule(self):
        settings = ShowdownSettings(
            iterations=3,
            bounds_mode="fixed",
            block_bounds=(
                [(0, 100), (0, 100), (0, 100), (0, 100)],
                [(0, 10), (0, 10), (0, 10), (0, 10)],
                [(0, 500), (0, 500), (0, 500), (0, 500)],
            ),
        )
        maxima = [settings.bounds_for_iteration(i)[0][1] for i in range(3)]
        assert maxima == [100.0, 10.0, 500.0]

    def test_short_list_cycles(self):
        settings = ShowdownSettings(
            bounds_mode="fixed",
            block_bounds=([(0, 100)], [(0, 10)]),
        )
        assert settings.bounds_for_iteration(0) == settings.bounds_for_iteration(2)
        assert settings.bounds_for_iteration(1) == settings.bounds_for_iteration(3)

    def test_single_schedule_is_reused(self):
        settings = ShowdownSettings(
            bounds_mode="fixed", block_bounds=((0, 100), (40, 60))
        )
        assert settings.bounds_for_iteration(0) == settings.bounds_for_iteration(9)

    def test_jobs_carry_the_iteration_schedule(self):
        specs = {1: [BotSpec(key=f"R{i}", path=SAMPLE_BOT) for i in range(20)]}
        settings = ShowdownSettings(
            variations=(1,),
            iterations=2,
            bounds_mode="fixed",
            block_bounds=([(0, 100)], [(0, 7)]),
        )
        jobs = build_jobs(specs, settings)
        assert [j["block_bounds"] for j in jobs] == [[(0.0, 100.0)], [(0.0, 7.0)]]

    def test_default_blocks_are_not_all_identical(self):
        """Four identical blocks would switch off the regime-change problem."""
        blocks = ShowdownSettings().bounds_for_iteration(0)
        assert len(set(blocks)) > 1, "the default schedule has nothing to detect"

    def test_random_is_the_default_and_no_two_iterations_share_a_schedule(self):
        settings = ShowdownSettings()
        assert settings.bounds_mode == "random"
        schedules = [tuple(settings.bounds_for_iteration(i)) for i in range(6)]
        assert len(set(schedules)) == 6

    def test_random_bounds_are_reproducible_from_the_seed(self):
        """A showdown has to be replayable, and every group inside an iteration
        has to face the same blocks or their standardised scores do not compare."""
        a = ShowdownSettings(seed=4242)
        b = ShowdownSettings(seed=4242)
        assert a.bounds_for_iteration(2) == b.bounds_for_iteration(2)
        assert ShowdownSettings(seed=4243).bounds_for_iteration(2) != a.bounds_for_iteration(2)


class TestValidateHandlesEveryStoredShape:
    """Regression: `/api/submit` 500'd for every participant on 09/09.

    `harness.validate.validate()` used to hand `block_bounds` straight to
    `ValueSampler`, which only understands a flat `[(lo, hi), ...]` schedule.
    The moment `server.store.DEFAULT_SETTINGS["block_bounds"]` became the
    nested per-iteration shape from `bounds_for_iteration` (§9), every upload
    hit `ValueError: too many values to unpack` inside the request handler and
    came back as a bare "Internal Server Error" — correct-looking code, wrong
    shape of data, and nothing here would have caught it since `validate()` had
    no test of its own.

    This does not need the sandbox: it fails at `ValueSampler.__init__`, before
    any bot ever runs, so it is pinned at that level and runs on every platform.
    """

    @pytest.mark.parametrize(
        "shape",
        [
            pytest.param(
                [[0.0, 100.0], [40.0, 60.0], [0.0, 400.0], [5.0, 25.0]],
                id="flat-schedule",
            ),
            pytest.param(
                [
                    [[0.0, 100.0], [40.0, 60.0], [0.0, 400.0], [5.0, 25.0]],
                    [[10.0, 30.0], [0.0, 250.0], [60.0, 90.0], [0.0, 50.0]],
                ],
                id="nested-per-iteration",
            ),
            pytest.param(None, id="none"),
        ],
    )
    def test_every_shape_normalises_to_something_valuesampler_accepts(self, shape):
        schedules = normalise_block_bounds(shape or [(0.0, 100.0)])
        # This is the exact call `ValueSampler.__init__` makes; the bug was a
        # `ValueError` raised right here, before a bot was ever loaded.
        assert all(len(pair) == 2 for pair in schedules[0])

    def test_the_actual_stored_default_does_not_crash(self):
        """Not a synthetic shape — the literal value a fresh database holds."""
        from server.store import DEFAULT_SETTINGS

        schedules = normalise_block_bounds(DEFAULT_SETTINGS["block_bounds"])
        ValueSampler(schedules[0], seed=12345, block_size=120)


class TestTheBoundsGrids:
    """The hidden bounds are drawn off two grids, not chosen by hand.

    The grids ARE published — participants are told the shape of the problem.
    What is withheld is the seed, so which of the 10,000 blocks they face is
    unknowable in advance and unrepeatable between showdowns.
    """

    def test_the_grids_are_exactly_as_published(self):
        from src.auction.distributions import BLOCK_MIN_CHOICES, BLOCK_RANGE_CHOICES

        assert BLOCK_MIN_CHOICES == tuple(range(10, 1001, 10))
        assert BLOCK_RANGE_CHOICES == tuple(range(100, 10001, 100))
        assert len(BLOCK_MIN_CHOICES) == len(BLOCK_RANGE_CHOICES) == 100

    def test_every_drawn_block_sits_on_the_grids(self):
        import random

        from src.auction.distributions import (
            BLOCK_MIN_CHOICES,
            BLOCK_RANGE_CHOICES,
            draw_block_bounds,
        )

        rng = random.Random(11)
        for _ in range(200):
            for lo, hi in draw_block_bounds(rng, 4):
                assert lo in BLOCK_MIN_CHOICES
                assert (hi - lo) in BLOCK_RANGE_CHOICES
                assert hi > lo

    def test_the_minimum_is_never_zero(self):
        """A bot must not be able to treat x as a draw from U[0, M] and read M
        off the largest value it has seen."""
        import random

        from src.auction.distributions import draw_block_bounds

        rng = random.Random(5)
        for _ in range(200):
            assert all(lo >= 10.0 for lo, _ in draw_block_bounds(rng, 4))

    def test_scale_and_width_move_independently(self):
        """Both grids span two orders of magnitude, and the floor does not
        predict the width — otherwise there is one block shape, not 10,000."""
        import random
        import statistics

        from src.auction.distributions import draw_block_bounds

        rng = random.Random(3)
        blocks = [b for _ in range(400) for b in draw_block_bounds(rng, 4)]
        lows = [lo for lo, _ in blocks]
        widths = [hi - lo for lo, hi in blocks]

        assert max(lows) / min(lows) >= 50
        assert max(widths) / min(widths) >= 50
        # Near-zero correlation: the draws are independent.
        assert abs(statistics.correlation(lows, widths)) < 0.15

    def test_a_seeded_draw_is_reproducible(self):
        import random

        from src.auction.distributions import draw_block_bounds

        assert draw_block_bounds(random.Random(9), 4) == draw_block_bounds(
            random.Random(9), 4
        )
