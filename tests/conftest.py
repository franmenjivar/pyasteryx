"""Shared fixtures for the test-suite."""

import pytest

from pyasteryx import Decoder
from pyasteryx.spec import SpecRegistry


@pytest.fixture(scope="session")
def registry() -> SpecRegistry:
    return SpecRegistry.with_bundled()


@pytest.fixture(scope="session")
def cat021_spec(registry):
    return registry.get(21)


@pytest.fixture
def decoder() -> Decoder:
    return Decoder()


@pytest.fixture
def cat021_block(cat021_spec):
    """A single-record CAT021 v2.6 data block with known field values.

    Items and their intended decoded values:
        I021/010  SAC=25, SIC=200
        I021/040  ATP=5, ARC=1, RC=1, RAB=0 (single extent)
        I021/080  TAddr="3C6DA9"
        I021/130  Lat=45.0 deg, Lon=45.0 deg
        I021/140  geometric_height=2000.0 ft
        I021/145  FL=350.0
        I021/170  TId="ABCD1234"
    """
    from tests.asterix_builder import build_block, encode_sixbit

    items = {
        "I021/010": bytes.fromhex("19C8"),
        "I021/040": bytes.fromhex("AC"),
        "I021/080": bytes.fromhex("3C6DA9"),
        "I021/130": bytes.fromhex("200000200000"),
        "I021/140": bytes.fromhex("0140"),
        "I021/145": bytes.fromhex("0578"),
        "I021/170": encode_sixbit("ABCD1234", 8),
    }
    return build_block(cat021_spec, items)



@pytest.fixture(scope="session")
def cat062_spec(registry):
    return registry.get(62, "1.18")


# I062/105 has an LSB of 180/2**25 degrees.
_WGS84_LSB = 180.0 / 2**25

#: Time of track carried by :func:`cat062_block`: 12:34:56.000 UTC.
CAT062_TIME_OF_TRACK = 45296.0


def _wgs84(degrees: float) -> int:
    return int(round(degrees / _WGS84_LSB))


@pytest.fixture
def cat062_block(cat062_spec):
    """A single-record CAT062 v1.18 data block with known field values.

    Items and their intended decoded values:
        I062/010  SAC=25, SIC=200
        I062/040  track number 1234
        I062/060  Mode 3/A 7421 (octal), validated
        I062/070  time of track 45296.0 s (12:34:56 UTC)
        I062/080  SRC=3 (triangulation), CNF=0 (confirmed), TSB=1 (first), FPC=1
        I062/105  45.0 N, 11.25 E
        I062/136  measured flight level 35000 ft (FL350)
        I062/185  Vx=+200 m/s, Vy=0  -> 388.77 kt, track angle 090
        I062/200  VERTA=1 (climb)
        I062/220  rate of climb +1600 ft/min
        I062/290  ages: TRK 1.0 s, SSR 2.0 s, MDS 3.0 s
        I062/380  ADR 3C6DA9, callsign DLH4AB
    """
    from tests.asterix_builder import build_block, encode_sixbit

    items = {
        "I062/010": bytes.fromhex("19C8"),
        "I062/040": (1234).to_bytes(2, "big"),
        "I062/060": (0o7421).to_bytes(2, "big"),
        "I062/070": int(round(CAT062_TIME_OF_TRACK * 128)).to_bytes(3, "big"),
        "I062/080": bytes([0x0D, 0x30]),
        "I062/105": _wgs84(45.0).to_bytes(4, "big") + _wgs84(11.25).to_bytes(4, "big"),
        "I062/136": (1400).to_bytes(2, "big"),
        "I062/185": (800).to_bytes(2, "big") + (0).to_bytes(2, "big"),
        "I062/200": bytes([0x04]),
        "I062/220": (256).to_bytes(2, "big"),
        "I062/290": bytes([0xB0, 4, 8, 12]),
        "I062/380": bytes([0xC0]) + bytes.fromhex("3C6DA9") + encode_sixbit("DLH4AB", 8),
    }
    return build_block(cat062_spec, items)
