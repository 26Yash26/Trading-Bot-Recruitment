"""Round loop + edge cases (0.C / 1.B)."""

import pytest

pytestmark = pytest.mark.skip(reason="0.C — engine not implemented yet")


def test_highest_bid_wins():
    ...


def test_tie_all_winners_get_full_payoff():
    ...


def test_illegal_bid_over_capital_becomes_zero():
    ...


def test_bid_clamped_to_max_bid():
    ...


def test_bankrupt_bot_is_eliminated_and_excluded_from_num_players():
    ...


def test_full_run_is_deterministic_for_a_fixed_seed():
    ...
