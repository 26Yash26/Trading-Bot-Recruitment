"""Payoff rules vs the problem-statement sample runs (§14).

Variations 1-3, three bots: x = [30, 50, 60], bids = [45, 55, 30], capital 100.
Bot 2 (bid 55) wins; Bot 1 (bid 45) is second.
    V1: caps -> [100,  95, 100]
    V2: caps -> [100, 105, 100]
    V3: caps -> [97.5, 105, 100]

Variation 4, six bots: x = [30, 50, 60, 20, 45, 55], bids = [45, 55, 30, 40, 50, 58].
X = 60, b1 = 58 <= X, so the top two are paid and ranks 3-5 fund them.
    caps -> [97.9, 102, 100, 98.6, 96.5, 105]
"""

import pytest

from src.auction import variations
from src.auction.distributions import FixedSampler
from src.auction.engine import run_game


# --- pure payoff functions ---------------------------------------------------

def test_payoff_v1():
    assert variations.payoff_v1(50, 55) == pytest.approx(-5.0)


def test_payoff_v2():
    assert variations.payoff_v2(60, 55) == pytest.approx(5.0)


def test_payoff_v3_winner_matches_v2_formula():
    assert variations.payoff_v3_winner(60, 55) == pytest.approx(5.0)


def test_payoff_v3_second_is_minus_half_surplus():
    assert variations.payoff_v3_second(60, 55) == pytest.approx(-2.5)


def test_payoff_v3_second_clamped_to_zero_when_surplus_negative():
    assert variations.payoff_v3_second(40, 55) == 0.0


# --- full sample run through the engine ------------------------------------

def _fixed_bid_bot(bid_value):
    class _Bot:
        def __init__(self, config):
            pass

        def get_bid(self, obs):
            return bid_value

    return _Bot


SAMPLE_BOTS = [_fixed_bid_bot(45), _fixed_bid_bot(55), _fixed_bid_bot(30)]
SAMPLE_SAMPLER = FixedSampler([[30.0, 50.0, 60.0]])


def _run(variation, bots=None, sampler=None):
    return run_game(
        bots or SAMPLE_BOTS,
        variation=variation,
        starting_capitals=100.0,
        block_bounds=[(0.0, 100.0)],
        seed=0,
        max_bid=1000.0,
        num_rounds=1,
        sampler=sampler or SAMPLE_SAMPLER,
    )


def test_v1_sample_run():
    caps = [p.final_capital for p in _run(1).players]
    assert caps == pytest.approx([100.0, 95.0, 100.0])


def test_v2_sample_run():
    caps = [p.final_capital for p in _run(2).players]
    assert caps == pytest.approx([100.0, 105.0, 100.0])


def test_v3_sample_run():
    caps = [p.final_capital for p in _run(3).players]
    assert caps == pytest.approx([97.5, 105.0, 100.0])


def test_v3_winner_is_bot_2_and_second_is_bot_1():
    result = _run(3)
    assert result.players[1].wins == 1
    assert result.players[0].wins == 0
    assert result.players[2].wins == 0


# --- variation 4 -------------------------------------------------------------

V4_BOTS = [
    _fixed_bid_bot(45), _fixed_bid_bot(55), _fixed_bid_bot(30),
    _fixed_bid_bot(40), _fixed_bid_bot(50), _fixed_bid_bot(58),
]
V4_SAMPLER = FixedSampler([[30.0, 50.0, 60.0, 20.0, 45.0, 55.0]])


def test_payoff_v4_pays_the_top_two_and_charges_ranks_three_to_five():
    # bids sorted desc: 58, 55, 50, 45, 40, 30 with X = 60.
    payoffs = variations.payoff_v4(60.0, [58, 55, 50, 45, 40, 30])
    assert payoffs == pytest.approx([5.0, 2.0, -3.5, -2.1, -1.4, 0.0])


def test_payoff_v4_round_is_zero_sum():
    assert sum(variations.payoff_v4(60.0, [58, 55, 50, 45, 40, 30])) == pytest.approx(0.0)


def test_payoff_v4_overbidding_the_field_max_costs_the_winner_alone():
    # b1 = 62 > X = 60: the winner eats 60 - 62 and no penalties are collected.
    payoffs = variations.payoff_v4(60.0, [62, 55, 50, 45, 40, 30])
    assert payoffs[0] == pytest.approx(-2.0)
    assert payoffs[1:] == pytest.approx([0.0] * 5)


def test_payoff_v4_renormalises_when_ranks_three_to_five_are_missing():
    """Four bidders: only ranks 3 and 4 exist, so they carry the whole penalty."""
    payoffs = variations.payoff_v4(60.0, [58, 55, 50, 45])
    assert sum(payoffs) == pytest.approx(0.0)
    # shares 0.5 and 0.3 renormalise to 0.625 and 0.375 of T = 7.
    assert payoffs[2] == pytest.approx(-0.625 * 7)
    assert payoffs[3] == pytest.approx(-0.375 * 7)


def test_payoff_v4_two_bidders_pay_no_penalty():
    payoffs = variations.payoff_v4(60.0, [58, 55])
    assert payoffs == pytest.approx([5.0, 2.0])


def test_v4_sample_run():
    caps = [p.final_capital for p in _run(4, V4_BOTS, V4_SAMPLER).players]
    assert caps == pytest.approx([97.9, 102.0, 100.0, 98.6, 96.5, 105.0])


def test_v4_winner_is_the_highest_bidder():
    result = _run(4, V4_BOTS, V4_SAMPLER)
    assert result.players[5].wins == 1
    assert sum(p.wins for p in result.players) == 1
