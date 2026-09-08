"""Runtime sandbox around participant code (1.A)."""

import pytest

pytestmark = pytest.mark.skip(reason="1.A — sandbox not implemented yet")


def test_slow_bot_times_out_and_bids_zero():
    ...


def test_memory_hog_is_disqualified():
    ...


def test_bot_cannot_open_sockets():
    ...


def test_bot_exception_becomes_zero_bid_and_is_logged():
    ...


def test_nan_negative_string_bids_are_rejected():
    ...
