"""Verifies the worked example in README.md against the real decoder.

The README shows 48 octets of CAT062 and the values they decode to. A reader
will copy those bytes and expect exactly those values back, so the example is
pinned here rather than left to drift as the specs or the Track view change.
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path

import pytest

from pyasteryx import Decoder, Track, tracks

README = Path(__file__).resolve().parent.parent / "README.md"

#: The record shown in the README's "From the wire to a track" section.
RAW = bytes.fromhex(
    "3E00309B5FA419C85878000080000000200000032000000F11"
    "C03C6DA910C23404282004D20D30B004080C0405780100"
)


@pytest.fixture(scope="module")
def readme() -> str:
    return README.read_text(encoding="utf-8")


def test_the_readme_still_contains_the_example(readme):
    assert "From the wire to a track" in readme


def test_the_hex_dump_in_the_readme_matches_these_bytes(readme):
    """Guards against the dump and the expectations drifting apart."""
    block = readme.split("From the wire to a track", 1)[1]
    dump = block.split("```", 2)[1]
    octets = re.findall(r"\b[0-9A-F]{2}\b", dump)
    assert bytes.fromhex("".join(octets)) == RAW


def test_it_is_one_48_octet_cat062_record():
    assert len(RAW) == 48
    (message,) = Decoder().decode(RAW)
    assert message.category == 62


def test_the_raw_items_are_as_shown():
    (message,) = Decoder().decode(RAW)
    assert message.items == {
        "I062/010": {"SAC": 25, "SIC": 200},
        "I062/070": {"ToT": 45296.0},
        "I062/105": {"Lat": 45.0, "Lon": 11.25},
        "I062/185": {"Vx": 200.0, "Vy": 0.0},
        "I062/060": {"V": 0, "G": 0, "CH": 0, "Mode3A": "7421"},
        "I062/380": {"ADR": {"ADR": "3C6DA9"}, "ID": {"ACID": "DLH4AB"}},
        "I062/040": {"TrkN": 1234},
        "I062/080": {
            "MON": 0, "SPI": 0, "MRH": 0, "SRC": 3, "CNF": 0,
            "SIM": 0, "TSE": 0, "TSB": 1, "FPC": 1, "AFF": 0, "STP": 0, "KOS": 0,
        },
        "I062/290": {"TRK": {"TRK": 1.0}, "SSR": {"SSR": 2.0}, "MDS": {"MDS": 3.0}},
        "I062/200": {"TRANSA": 0, "LONGA": 0, "VERTA": 1, "ADF": 0},
        "I062/136": {"MFL": 35000.0},
        "I062/220": {"RoC": 1600.0},
    }


def test_the_track_values_are_as_shown():
    (track,) = tracks(Decoder().decode(RAW), day=datetime.date(2026, 9, 5))
    assert track.timestamp == datetime.datetime(
        2026, 9, 5, 12, 34, 56, tzinfo=datetime.timezone.utc
    )
    assert track.track_number == 1234
    assert track.callsign == "DLH4AB"
    assert track.address == "3C6DA9"
    assert track.mode_3a == "7421"
    assert track.position == (45.0, 11.25)
    assert track.flight_level == 350.0
    assert track.measured_altitude_ft == 35000.0
    assert track.ground_speed_kt == 388.76889848812095
    assert track.track_angle_deg == 90.0
    assert track.vertical_rate_fpm == 1600.0
    assert track.vertical_mode == "climb"
    assert track.transversal_mode == "constant course"
    assert track.altitude_source == "triangulation"
    assert track.is_confirmed is True
    assert track.is_first_report is True
    assert track.is_last_report is False
    assert track.flight_plan_correlated is True
    assert track.contributing_sensors == ("SSR", "MDS")


def test_the_annotated_item_list_matches_what_the_fspec_selects(readme):
    """Every I062/NNN named in the byte-layout annotation is really present."""
    layout = readme.split("FSPEC — 3 octets", 1)[1].split("```", 1)[0]
    annotated = set(re.findall(r"I062/\d{3}", layout))
    (message,) = Decoder().decode(RAW)
    assert annotated == set(message.items)


def test_the_raw_items_remain_reachable_from_the_track():
    """The README promises the raw items are still on t.message."""
    (track,) = tracks(Decoder().decode(RAW))
    assert isinstance(track, Track)
    assert track.message.items["I062/185"] == {"Vx": 200.0, "Vy": 0.0}
