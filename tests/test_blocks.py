"""Block boundaries and scoring (problem statement §3.1 and §8).

The two rules that make this competition what it is: capital does not carry
across a block, and raw profit is never compared directly, it is normalised by
the block's hidden maximum and then standardised inside the group.
"""

import pytest

from src.auction import scoring
from src.auction.capital import CapitalDraw
from src.auction.distributions import FixedSampler
from src.auction.engine import run_game


def fixed_bid_bot(bid_value):
    class _Bot:
        def __init__(self, config):
            pass

        def get_bid(self, obs):
            return bid_value

    return _Bot


def spy_bot(record):
    class _Bot:
        def __init__(self, config):
            pass

        def get_bid(self, obs):
            record.append(dict(obs))
            return 0.0

    return _Bot


# --- step 1: scale normalisation ----------------------------------------------


def test_normalised_profit_is_measured_in_units_of_the_block_maximum():
    assert scoring.normalised_profit(100.0, 130.0, 50.0) == pytest.approx(0.6)


def test_a_bankrupt_bot_loses_its_whole_starting_capital():
    assert scoring.normalised_profit(80.0, 0.0, 40.0) == pytest.approx(-2.0)


def test_normalised_profit_of_a_degenerate_block_is_zero():
    assert scoring.normalised_profit(10.0, 20.0, 0.0) == 0.0


# --- step 2: within-group standardisation -------------------------------------


def test_block_points_centre_on_fifty_and_move_fifteen_per_standard_deviation():
    points = scoring.block_points([-1.0, 0.0, 1.0])
    assert points[1] == pytest.approx(50.0)
    # pstdev of (-1, 0, 1) is sqrt(2/3); +1 is that many sigmas above the mean.
    assert points[2] == pytest.approx(50.0 + 15.0 * (1.0 / (2 / 3) ** 0.5))
    assert points[0] == pytest.approx(100.0 - points[2])


def test_block_points_are_clipped_at_three_sigma():
    """One freak result must not be allowed to decide the competition."""
    points = scoring.block_points([0.0] * 19 + [1000.0])
    assert max(points) == pytest.approx(95.0)
    assert min(points) >= 5.0


def test_block_points_are_all_centre_when_nobody_is_separated():
    assert scoring.block_points([0.4, 0.4, 0.4]) == pytest.approx([50.0, 50.0, 50.0])


def test_iteration_score_is_the_sum_of_the_block_scores():
    assert scoring.iteration_score([50.0, 60.0, 40.0, 55.0]) == pytest.approx(205.0)


# --- capital draw --------------------------------------------------------------


def test_capital_draw_stays_inside_the_problem_statement_range():
    import random

    rng = random.Random(7)
    draw = CapitalDraw()
    for _ in range(200):
        # C = m_b + (M_b - m_b) * kappa, kappa in [0.5, 2.5].
        capital = draw.draw(rng, 200.0, 1200.0)
        assert 200.0 + 1000.0 * 0.5 <= capital <= 200.0 + 1000.0 * 2.5


def test_capital_is_the_floor_plus_kappa_block_widths():
    """The reason the formula uses the range rather than the maximum.

    kappa means "how many block-widths of headroom I start with", and that
    meaning has to hold whatever the block looks like. Two blocks can share a
    maximum of 1100 and be completely different games, [1000, 1100], where
    every value sits within 10% of every other, against [10, 1100], which spans
    two orders of magnitude. Scaling capital by M_b would hand out the same
    bankroll in both; scaling by the width does not.
    """
    import random

    narrow = CapitalDraw().draw(random.Random(1), 1000.0, 1100.0)
    wide = CapitalDraw().draw(random.Random(1), 10.0, 1100.0)

    # Same seed, so the same kappa: the headroom above the floor is exactly
    # kappa block-widths in each, and the two widths differ by 10.9x.
    assert (wide - 10.0) / (narrow - 1000.0) == pytest.approx(1090.0 / 100.0)

    kappa_narrow = (narrow - 1000.0) / 100.0
    kappa_wide = (wide - 10.0) / 1090.0
    assert kappa_narrow == pytest.approx(kappa_wide)
    assert 0.5 <= kappa_narrow <= 2.5


def test_capital_is_always_positive_on_the_published_grids():
    """m_b >= 10 and range >= 100, so the smallest draw is 10 + 100*0.5 = 60.
    That is what lets the formula drop the old floor and jitter terms."""
    import random

    from src.auction.distributions import BLOCK_MIN_CHOICES, BLOCK_RANGE_CHOICES

    rng = random.Random(0)
    draw = CapitalDraw()
    smallest = draw.draw(rng, min(BLOCK_MIN_CHOICES),
                         min(BLOCK_MIN_CHOICES) + min(BLOCK_RANGE_CHOICES))
    assert smallest >= 60.0

    for _ in range(500):
        lo = float(rng.choice(BLOCK_MIN_CHOICES))
        hi = lo + float(rng.choice(BLOCK_RANGE_CHOICES))
        assert draw.draw(rng, lo, hi) >= 60.0


# --- the engine's block loop ---------------------------------------------------


BOUNDS = [(0.0, 100.0), (0.0, 100.0)]


def test_capital_is_redrawn_at_a_block_boundary_and_does_not_carry_over():
    """Bot 0 wins every round at a loss, so it would be far behind by block 2."""
    result = run_game(
        [fixed_bid_bot(5), fixed_bid_bot(1)],
        variation=1,
        block_bounds=BOUNDS,
        seed=11,
        num_rounds=4,
        block_size=2,
        capital_draw=CapitalDraw(),
        # A non-degenerate block: capital scales with the width, so a sampler
        # with no width at all would hand every player a capital of zero.
        sampler=FixedSampler([[0.0, 50.0]] * 4),
    )
    blocks = result.players[0].blocks
    assert len(blocks) == 2
    # The second block starts on a fresh draw, not on where the first one ended.
    assert blocks[1].start_capital != pytest.approx(blocks[0].end_capital)


def all_in_bot():
    """Bids its entire capital every round, wins, and overpays, every time."""

    class _Bot:
        def __init__(self, config):
            pass

        def get_bid(self, obs):
            return obs["capital"]

    return _Bot


class ZeroValueSampler(FixedSampler):
    """Every value is zero, but the block still has a real hidden maximum.

    Winning therefore costs exactly the bid, which is what makes bankruptcy
    reachable in one round for a bot that bids everything.
    """

    def bounds_for_round(self, round_idx):
        return (0.0, 100.0)


def test_a_bankrupt_bot_returns_at_the_next_block():
    result = run_game(
        [all_in_bot(), fixed_bid_bot(1)],
        variation=1,
        block_bounds=BOUNDS,
        seed=5,
        num_rounds=20,
        block_size=10,
        capital_draw=CapitalDraw(),
        sampler=ZeroValueSampler([[0.0, 0.0]] * 20),
    )
    blocks = result.players[0].blocks
    assert blocks[0].bankrupt                       # spent itself to zero
    assert blocks[0].normalised_profit < 0
    assert blocks[1].start_capital > 0              # revived on a fresh draw
    assert result.players[0].blocks_survived < len(blocks)


def test_every_block_is_scored_and_the_iteration_score_sums_them():
    result = run_game(
        [fixed_bid_bot(3), fixed_bid_bot(7), fixed_bid_bot(1)],
        variation=2,
        block_bounds=[(0.0, 100.0)] * 4,
        seed=42,
        num_rounds=400,
        block_size=100,
        capital_draw=CapitalDraw(),
    )
    assert result.num_blocks == 4
    for player in result.players:
        assert len(player.blocks) == 4
        assert player.iteration_score == pytest.approx(
            sum(b.points for b in player.blocks)
        )
    # Standardisation is within-group, so each block's points average out to 50.
    for index in range(4):
        column = [p.blocks[index].points for p in result.players]
        assert sum(column) / len(column) == pytest.approx(50.0)


# --- what the bot is told ------------------------------------------------------


def test_the_observation_matches_the_problem_statement_table():
    record = []
    run_game(
        [spy_bot(record), fixed_bid_bot(4), fixed_bid_bot(2)],
        variation=2,
        block_bounds=[(0.0, 100.0)],
        seed=1,
        num_rounds=3,
        block_size=500,
        capital_draw=CapitalDraw(),
    )
    first, second = record[0], record[1]

    assert first["round"] == 1                       # rounds are 1-indexed (§5)
    assert set(first) == {
        "round", "x", "capital", "max_bid", "num_players",
        "highest_bid_last_round", "second_highest_bid_last_round",
        "my_last_bid", "my_last_rank", "my_last_payoff",
        "max_value_last_round",                       # variations 2-4 only
    }
    assert first["max_bid"] == pytest.approx(first["capital"])
    assert first["highest_bid_last_round"] == 0.0     # nothing has happened yet
    assert second["highest_bid_last_round"] == pytest.approx(4.0)
    assert second["second_highest_bid_last_round"] == pytest.approx(2.0)


def test_variation_one_is_not_told_the_field_maximum():
    record = []
    run_game(
        [spy_bot(record), fixed_bid_bot(4)],
        variation=1,
        block_bounds=[(0.0, 100.0)],
        seed=1,
        num_rounds=2,
        block_size=500,
        capital_draw=CapitalDraw(),
    )
    assert "max_value_last_round" not in record[0]


def test_variation_four_is_told_the_top_five_bids():
    record = []
    run_game(
        [spy_bot(record)] + [fixed_bid_bot(b) for b in (9, 8, 7, 6, 5)],
        variation=4,
        block_bounds=[(0.0, 100.0)],
        seed=1,
        num_rounds=2,
        block_size=500,
        capital_draw=CapitalDraw(),
    )
    assert record[1]["top_bids_last_round"] == pytest.approx([9.0, 8.0, 7.0, 6.0, 5.0])


def test_a_bid_above_capital_is_filed_as_zero_with_no_fixed_ceiling():
    """There is no max_bid any more, your capital is the ceiling (§3)."""
    result = run_game(
        [fixed_bid_bot(10_000), fixed_bid_bot(1)],
        variation=1,
        block_bounds=[(0.0, 100.0)],
        seed=2,
        num_rounds=1,
        block_size=500,
        capital_draw=CapitalDraw(),
        sampler=FixedSampler([[50.0, 50.0]]),
    )
    # Bot 0's bid was voided, so bot 1 wins with a bid of 1.
    assert result.players[1].wins == 1
    assert result.players[0].wins == 0
