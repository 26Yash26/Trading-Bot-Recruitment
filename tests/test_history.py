"""Rolling bid history window (0.C)."""

from src.auction.history import BidHistory


def test_empty_history_reports_zero_and_empty_series():
    h = BidHistory(window=100)
    assert h.highest_last_100() == 0.0
    assert h.second_highest_last_100() == 0.0
    assert h.highest_series() == []
    assert h.second_series() == []


def test_window_only_keeps_last_n_rounds():
    h = BidHistory(window=100)
    for r in range(150):
        h.record(round_highest=float(r), round_second=float(r) - 1)
    assert len(h.highest_series()) == 100
    assert len(h.second_series()) == 100
    # oldest kept round is 50
    assert h.highest_series()[0] == 50.0
    assert h.highest_series()[-1] == 149.0


def test_scalars_are_max_over_the_window():
    h = BidHistory(window=3)
    h.record(10, 4)
    h.record(30, 9)
    h.record(20, 25)
    assert h.highest_last_100() == 30.0
    assert h.second_highest_last_100() == 25.0
    # roll the window twice so the 30/9 round drops out; kept: (20,25),(15,5),(12,3)
    h.record(15, 5)
    h.record(12, 3)
    assert h.highest_last_100() == 20.0
    assert h.second_highest_last_100() == 25.0


def test_series_stay_aligned():
    h = BidHistory(window=10)
    h.record(5, 3)
    h.record(8, 1)
    assert h.highest_series() == [5.0, 8.0]
    assert h.second_series() == [3.0, 1.0]
