"""End-to-end tests for the CAT062 track view.

The expected values below are derived by hand from the CAT062 specification, so
these tests pin both the octet-level decoding and the engineering-unit
conversions in :mod:`pyasteryx.track`.
"""

from __future__ import annotations

import datetime

import pytest

from pyasteryx import Track, group_by_track, tracks
from tests.asterix_builder import build_block
from tests.conftest import CAT062_TIME_OF_TRACK

@pytest.fixture
def track(decoder, cat062_block) -> Track:
    (message,) = decoder.decode(cat062_block)
    return Track(message, day=datetime.date(2026, 9, 5))


class TestIdentity:
    def test_source(self, track):
        assert track.sac == 25
        assert track.sic == 200
        assert track.source == (25, 200)

    def test_track_number(self, track):
        assert track.track_number == 1234

    def test_callsign(self, track):
        assert track.callsign == "DLH4AB"

    def test_icao_address(self, track):
        assert track.address == "3C6DA9"

    def test_mode_3a_is_octal(self, track):
        assert track.mode_3a == "7421"
        assert track.mode_3a_valid is True


class TestTime:
    def test_time_of_track_is_seconds_since_midnight(self, track):
        assert track.time_of_track == pytest.approx(CAT062_TIME_OF_TRACK)

    def test_timestamp_uses_the_supplied_day(self, track):
        assert track.timestamp == datetime.datetime(
            2026, 9, 5, 12, 34, 56, tzinfo=datetime.timezone.utc
        )

    def test_timestamp_is_none_without_a_day(self, decoder, cat062_block):
        (message,) = decoder.decode(cat062_block)
        assert Track(message).timestamp is None


class TestGeometry:
    def test_position(self, track):
        assert track.latitude == pytest.approx(45.0)
        assert track.longitude == pytest.approx(11.25)
        assert track.position == pytest.approx((45.0, 11.25))

    def test_altitude(self, track):
        assert track.measured_altitude_ft == pytest.approx(35000.0)
        assert track.flight_level == pytest.approx(350.0)

    def test_ground_speed_from_cartesian_velocity(self, track):
        # 200 m/s == 388.77 kt
        assert track.velocity_ms == pytest.approx((200.0, 0.0))
        assert track.ground_speed_kt == pytest.approx(200.0 * 3600 / 1852)

    def test_track_angle_east_is_090(self, track):
        # Vx is the easterly component, so a pure +Vx is a track of 090.
        assert track.track_angle_deg == pytest.approx(90.0)

    def test_vertical_rate(self, track):
        assert track.vertical_rate_fpm == pytest.approx(1600.0)


class TestStatus:
    def test_lifecycle_flags(self, track):
        assert track.is_first_report is True
        assert track.is_last_report is False
        assert track.is_confirmed is True
        assert track.flight_plan_correlated is True

    def test_coded_fields_are_described(self, track):
        assert track.altitude_source == "triangulation"
        assert track.vertical_mode == "climb"

    def test_no_emergency_reads_as_none(self, track):
        assert track.emergency is None

    def test_contributing_sensors_excludes_the_track_age(self, track):
        assert track.contributing_sensors == ("SSR", "MDS")
        assert track.update_ages == {"TRK": 1.0, "SSR": 2.0, "MDS": 3.0}

    def test_absent_items_are_none_not_errors(self, decoder, cat062_spec):
        """A minimal record must not raise on any accessor."""
        block = build_block(cat062_spec, {"I062/010": bytes.fromhex("19C8")})
        (message,) = decoder.decode(block)
        bare = Track(message)
        assert bare.track_number is None
        assert bare.callsign is None
        assert bare.position is None
        assert bare.ground_speed_kt is None
        assert bare.emergency is None
        assert bare.contributing_sensors == ()


class TestVelocityPreference:
    def test_aircraft_derived_speed_wins_over_cartesian(self, decoder, cat062_spec):
        """I062/380 GSP and TAN are measured, so they beat the tracker's estimate."""
        # TAN and GSP are subfields 17 and 18, so the primary subfield needs a
        # third octet: two FX-only octets, then bits 0x20 and 0x10.
        gsp = int(round(300.0 / 3600 / 2**-14))  # 300 kt in units of 2**-14 NM/s
        tan = int(round(270.0 / (360 / 2**16)))  # 270 degrees true
        block = build_block(
            cat062_spec,
            {
                "I062/185": (800).to_bytes(2, "big") + (0).to_bytes(2, "big"),
                "I062/380": bytes([0x01, 0x01, 0x30])
                + tan.to_bytes(2, "big")
                + gsp.to_bytes(2, "big"),
            },
        )
        (message,) = decoder.decode(block)
        trk = Track(message)
        assert trk.ground_speed_kt == pytest.approx(300.0, abs=0.1)
        assert trk.track_angle_deg == pytest.approx(270.0, abs=0.01)


class TestToDict:
    def test_row_has_stable_named_columns(self, track):
        row = track.to_dict()
        assert row["callsign"] == "DLH4AB"
        assert row["track_number"] == 1234
        assert row["flight_level"] == pytest.approx(350.0)
        assert row["vertical_mode"] == "climb"
        # No raw item keys leak in by default.
        assert not any(key.startswith("I062/") for key in row)

    def test_include_raw_merges_the_item_keys(self, track):
        row = track.to_dict(include_raw=True)
        assert row["I062/040.TrkN"] == 1234
        assert "category" not in row


class TestTracksHelper:
    def test_skips_other_categories(self, decoder, cat021_block, cat062_block):
        messages = decoder.decode(cat021_block + cat062_block)
        assert [m.category for m in messages] == [21, 62]
        result = list(tracks(messages))
        assert len(result) == 1
        assert result[0].track_number == 1234

    def test_day_is_propagated(self, decoder, cat062_block):
        day = datetime.date(2026, 1, 2)
        (trk,) = tracks(decoder.decode(cat062_block), day=day)
        assert trk.timestamp.date() == day

    def test_group_by_track_keys_on_source_and_number(self, decoder, cat062_block):
        messages = decoder.decode(cat062_block * 3)
        grouped = group_by_track(tracks(messages))
        assert list(grouped) == [(25, 200, 1234)]
        assert len(grouped[(25, 200, 1234)]) == 3

    def test_group_by_track_number_only(self, decoder, cat062_block):
        grouped = group_by_track(tracks(decoder.decode(cat062_block)), by_source=False)
        assert list(grouped) == [1234]
