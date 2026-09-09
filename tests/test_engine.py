"""Round loop + edge cases (0.C)."""

import pytest

from src.auction.distributions import FixedSampler
from src.auction.engine import run_game


def fixed_bid_bot(bid_value):
    class _Bot:
        def __init__(self, config):
            self.config = config

        def get_bid(self, obs):
            return bid_value

    return _Bot


def spy_bot(record):
    """Records every obs it sees into ``record`` (a list); bids 0."""

    class _Bot:
        def __init__(self, config):
            record.append(("config", config))

        def get_bid(self, obs):
            record.append(("obs", dict(obs)))
            return 0.0

    return _Bot


def test_highest_bid_wins():
    result = run_game(
        [fixed_bid_bot(10), fixed_bid_bot(20)],
        variation=1,
        starting_capitals=100.0,
        block_bounds=[(0.0, 100.0)],
        seed=0,
        max_bid=1000.0,
        num_rounds=1,
        sampler=FixedSampler([[40.0, 40.0]]),
    )
    assert result.players[1].wins == 1
    assert result.players[0].wins == 0


def test_tie_all_winners_get_full_payoff():
    # both bid 20; V2 payoff for a winner = X - 20 = 50 - 20 = 30, each.
    result = run_game(
        [fixed_bid_bot(20), fixed_bid_bot(20)],
        variation=2,
        starting_capitals=100.0,
        block_bounds=[(0.0, 100.0)],
        seed=0,
        max_bid=1000.0,
        num_rounds=1,
        sampler=FixedSampler([[50.0, 10.0]]),
    )
    assert result.players[0].wins == 1
    assert result.players[1].wins == 1
    assert result.players[0].net_profit == pytest.approx(30.0)
    assert result.players[1].net_profit == pytest.approx(30.0)


def test_illegal_bid_over_capital_becomes_zero():
    # bot 0 bids 500 but only has 100 -> bid treated as 0, so bot 1 (bid 10) wins.
    result = run_game(
        [fixed_bid_bot(500), fixed_bid_bot(10)],
        variation=1,
        starting_capitals=100.0,
        block_bounds=[(0.0, 100.0)],
        seed=0,
        max_bid=1000.0,
        num_rounds=1,
        sampler=FixedSampler([[40.0, 40.0]]),
    )
    assert result.players[1].wins == 1
    assert result.players[0].wins == 0


def test_bid_clamped_to_max_bid():
    # bot 0 bids 999 but max_bid is 50 -> effective bid 50; wins; V1 payoff = 40 - 50 = -10.
    result = run_game(
        [fixed_bid_bot(999), fixed_bid_bot(40)],
        variation=1,
        starting_capitals=100.0,
        block_bounds=[(0.0, 100.0)],
        seed=0,
        max_bid=50.0,
        num_rounds=1,
        sampler=FixedSampler([[40.0, 10.0]]),
    )
    assert result.players[0].wins == 1
    assert result.players[0].net_profit == pytest.approx(-10.0)


def test_bankrupt_bot_starts_inactive_and_is_excluded_from_num_players():
    record = []
    run_game(
        [spy_bot(record), fixed_bid_bot(5), fixed_bid_bot(5)],
        variation=1,
        starting_capitals=[0.0, 100.0, 100.0],  # spy bot is broke from the start
        block_bounds=[(0.0, 100.0)],
        seed=0,
        max_bid=100.0,
        num_rounds=1,
        sampler=FixedSampler([[10.0, 10.0]]),  # only 2 active players
    )
    obs_seen = [entry for kind, entry in record if kind == "obs"]
    assert obs_seen == []  # spy bot was never asked, it was inactive


def test_bot_is_eliminated_the_round_its_capital_hits_zero():
    # values are always 0; bot 0 bids 5 and wins every round (bot 1 bids 1).
    # V1 payoff each round = 0 - 5 = -5. Starting capital 10 -> 5 -> 0 (eliminated).
    result = run_game(
        [fixed_bid_bot(5), fixed_bid_bot(1)],
        variation=1,
        starting_capitals=[10.0, 100.0],
        block_bounds=[(0.0, 100.0)],
        seed=0,
        max_bid=1000.0,
        num_rounds=10,
        sampler=FixedSampler([[0.0, 0.0]] * 10),
    )
    assert result.players[0].eliminated_round == 1
    assert result.rounds_played == 2  # round 2 has < 2 active players -> stop


def test_all_zero_bids_everyone_wins_and_pockets_their_value():
    # DOCUMENTS CURRENT BEHAVIOUR (see docs/bot_interface.md open decision):
    # the literal rules say highest bid wins and ties all win, so when every bid
    # is 0 the whole field "wins" and each gets payoff x_i - 0 = x_i for free.
    result = run_game(
        [fixed_bid_bot(0), fixed_bid_bot(0)],
        variation=1,
        starting_capitals=100.0,
        block_bounds=[(0.0, 100.0)],
        seed=0,
        max_bid=100.0,
        num_rounds=1,
        sampler=FixedSampler([[30.0, 70.0]]),
    )
    assert result.players[0].net_profit == pytest.approx(30.0)
    assert result.players[1].net_profit == pytest.approx(70.0)


def test_full_run_is_deterministic_for_a_fixed_seed():
    kw = dict(
        variation=2,
        starting_capitals=100.0,
        block_bounds=[(0.0, 100.0), (10.0, 90.0), (0.0, 50.0), (20.0, 80.0)],
        seed=123,
        max_bid=100.0,
        num_rounds=300,
    )
    bots = [fixed_bid_bot(30), fixed_bid_bot(45), fixed_bid_bot(10)]
    r1 = run_game(list(bots), **kw)
    r2 = run_game(list(bots), **kw)
    assert [p.final_capital for p in r1.players] == [p.final_capital for p in r2.players]
    assert r1.capital_by_round == r2.capital_by_round
