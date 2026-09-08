"""Per-block uniform sampling (0.C)."""

import numpy as np
import pytest

from src.auction.distributions import ValueSampler


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
