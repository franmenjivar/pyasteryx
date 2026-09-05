"""Tests for ASTERIX time-of-day handling."""

from __future__ import annotations

import datetime

from pyasteryx.timing import SECONDS_PER_DAY, TOD_LSB, DayResolver, to_datetime, to_timedelta

UTC = datetime.timezone.utc


def test_lsb_is_one_128th_of_a_second():
    assert TOD_LSB == 1 / 128


def test_to_datetime_combines_day_and_time():
    assert to_datetime(45296.0, datetime.date(2026, 9, 5)) == datetime.datetime(
        2026, 9, 5, 12, 34, 56, tzinfo=UTC
    )


def test_to_datetime_is_timezone_aware_utc():
    assert to_datetime(0.0, datetime.date(2026, 1, 1)).tzinfo is UTC


def test_to_datetime_rolls_past_midnight():
    """A counter that ran past 86400 belongs to the next day."""
    result = to_datetime(SECONDS_PER_DAY + 60, datetime.date(2026, 9, 5))
    assert result == datetime.datetime(2026, 9, 6, 0, 1, tzinfo=UTC)


def test_to_timedelta():
    assert to_timedelta(90.5) == datetime.timedelta(seconds=90.5)


class TestDayResolver:
    def test_holds_the_day_while_time_advances(self):
        resolver = DayResolver(datetime.date(2026, 9, 5))
        assert resolver.resolve(10.0).date() == datetime.date(2026, 9, 5)
        assert resolver.resolve(20.0).date() == datetime.date(2026, 9, 5)
        assert resolver.resolve(86000.0).date() == datetime.date(2026, 9, 5)

    def test_advances_the_day_on_a_midnight_wrap(self):
        resolver = DayResolver(datetime.date(2026, 9, 5))
        resolver.resolve(86399.0)
        wrapped = resolver.resolve(0.5)
        assert wrapped.date() == datetime.date(2026, 9, 6)
        assert resolver.day == datetime.date(2026, 9, 6)

    def test_small_backwards_jumps_are_out_of_order_delivery_not_a_wrap(self):
        """Feeds deliver a few seconds out of order; that must not roll the date."""
        resolver = DayResolver(datetime.date(2026, 9, 5))
        resolver.resolve(1000.0)
        assert resolver.resolve(995.0).date() == datetime.date(2026, 9, 5)
        assert resolver.day == datetime.date(2026, 9, 5)

    def test_defaults_to_today_utc(self):
        assert DayResolver().day == datetime.datetime.now(UTC).date()

    def test_reset_forgets_the_previous_time(self):
        resolver = DayResolver(datetime.date(2026, 9, 5))
        resolver.resolve(86399.0)
        resolver.reset()
        assert resolver.resolve(0.5).date() == datetime.date(2026, 9, 5)

    def test_reset_can_re_anchor_the_day(self):
        resolver = DayResolver(datetime.date(2026, 9, 5))
        resolver.reset(datetime.date(2027, 1, 1))
        assert resolver.day == datetime.date(2027, 1, 1)
