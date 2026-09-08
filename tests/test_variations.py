"""Payoff rules vs the problem-statement sample run (§10).

x = [30, 50, 60], bids = [45, 55, 30], capital 100 each.
Bot 2 (bid 55) wins; Bot 1 (bid 45) is second.
    V1: caps -> [100,  95, 100]
    V2: caps -> [100, 105, 100]
    V3: caps -> [97.5, 105, 100]
"""

import pytest

pytestmark = pytest.mark.skip(reason="0.C — variations not implemented yet")


def test_v1_sample_run():
    ...


def test_v2_sample_run():
    ...


def test_v3_sample_run():
    ...


def test_v3_second_payoff_clamped_at_zero_when_value_below_bid():
    ...
