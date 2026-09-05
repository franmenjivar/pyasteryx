"""ASTERIX time-of-day handling.

Every ASTERIX time field (CAT062 I062/070, CAT021 I021/073, CAT048 I048/140, ...)
carries *seconds since midnight UTC* — never a date. The wire value is a 24-bit
counter with an LSB of 1/128 s, so the decoder already scales it to a float
number of seconds; what it cannot know is *which day* that midnight belonged to.

This module supplies the missing day. Two helpers cover the realistic cases:

* :func:`to_datetime` — you know the UTC date of the recording.
* :class:`DayResolver` — a stateful resolver for a live or recorded feed, which
  anchors on a reference date and rolls the date forward when the time-of-day
  counter wraps through midnight.

The wrap detection matters: a feed that runs across midnight emits ``86399.9``
then ``0.008``, and naive code produces a 24-hour backwards jump in the middle
of a trajectory.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional

__all__ = [
    "SECONDS_PER_DAY",
    "TOD_LSB",
    "DayResolver",
    "to_datetime",
    "to_timedelta",
]

SECONDS_PER_DAY = 86400.0

#: Resolution of an ASTERIX time-of-day field: 1/128 second.
TOD_LSB = 1.0 / 128.0

# A backwards jump larger than this is read as a midnight wrap rather than as
# out-of-order delivery. Feeds routinely deliver a few seconds out of order;
# they do not deliver 12 hours out of order.
_WRAP_THRESHOLD = SECONDS_PER_DAY / 2.0


def to_timedelta(seconds_since_midnight: float) -> timedelta:
    """Return an ASTERIX time-of-day as a :class:`~datetime.timedelta`."""
    return timedelta(seconds=seconds_since_midnight)


def to_datetime(seconds_since_midnight: float, day: date) -> datetime:
    """Combine an ASTERIX time-of-day with a UTC ``day`` into a UTC datetime.

    Args:
        seconds_since_midnight: The decoded time-of-day, in seconds.
        day: The UTC date whose midnight the counter is measured from.

    Returns:
        A timezone-aware :class:`~datetime.datetime` in UTC.

    Note:
        Values at or beyond 86400 s roll into the following day, which is what a
        recording that crossed midnight without resetting its counter looks like.
    """
    midnight = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    return midnight + timedelta(seconds=seconds_since_midnight)


class DayResolver:
    """Turns a stream of times-of-day into absolute UTC datetimes.

    ASTERIX time-of-day resets to zero at midnight. Feeding the values through
    one resolver keeps a monotonic date: when the counter jumps backwards by more
    than twelve hours, the resolver advances to the next day.

    Args:
        day: The UTC date the feed starts on. Defaults to today (UTC), which is
            the right answer for a live feed.

    Example::

        resolver = DayResolver()
        for msg in decoder.iter_udp("239.1.1.1", 8600):
            ts = resolver.resolve(msg["I062/070"]["ToT"])
    """

    __slots__ = ("_day", "_last")

    def __init__(self, day: Optional[date] = None) -> None:
        self._day: date = day if day is not None else datetime.now(timezone.utc).date()
        self._last: Optional[float] = None

    @property
    def day(self) -> date:
        """The UTC date the resolver is currently anchored on."""
        return self._day

    def resolve(self, seconds_since_midnight: float) -> datetime:
        """Return the absolute UTC datetime for one time-of-day value.

        Detects the midnight wrap by comparing against the previous value, so
        call this once per record, in delivery order.
        """
        last = self._last
        if last is not None and (last - seconds_since_midnight) > _WRAP_THRESHOLD:
            self._day = self._day + timedelta(days=1)
        self._last = seconds_since_midnight
        return to_datetime(seconds_since_midnight, self._day)

    def reset(self, day: Optional[date] = None) -> None:
        """Re-anchor the resolver, forgetting the previous time-of-day."""
        if day is not None:
            self._day = day
        self._last = None
