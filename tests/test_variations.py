"""Payoff rules vs the problem-statement sample run (§10).

x = [30, 50, 60], bids = [45, 55, 30], capital 100 each.
Bot 2 (bid 55) wins; Bot 1 (bid 45) is second.
    V1: caps -> [100,  95, 100]
    V2: caps -> [100, 105, 100]
    V3: caps -> [97.5, 105, 100]
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


def _run(variation):
    return run_game(
        SAMPLE_BOTS,
        variation=variation,
        starting_capitals=100.0,
        block_bounds=[(0.0, 100.0)],
        seed=0,
        max_bid=1000.0,
        num_rounds=1,
        sampler=SAMPLE_SAMPLER,
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
