"""Tests for the coded-field meaning tables."""

from __future__ import annotations

from pyasteryx.enums import CAT062, TABLES, describe


def test_describes_a_known_code():
    assert describe(62, "I062/080", "SRC", 3) == "triangulation"


def test_describes_a_flag():
    assert describe(62, "I062/080", "SIM", 1) == "simulated track"


def test_unknown_code_is_none():
    assert describe(62, "I062/080", "SRC", 99) is None


def test_unknown_field_is_none():
    assert describe(62, "I062/080", "NOPE", 0) is None


def test_unknown_item_is_none():
    assert describe(62, "I062/999", "SRC", 0) is None


def test_unknown_category_is_none():
    assert describe(999, "I062/080", "SRC", 0) is None


def test_unhashable_value_is_none_not_an_error():
    """describe() runs over every field of every record, so it must never raise."""
    assert describe(62, "I062/080", "SRC", {"unhashable": True}) is None
    assert describe(62, "I062/080", "SRC", None) is None


def test_tables_are_registered_per_category():
    assert set(TABLES) == {21, 48, 62}
    assert TABLES[62] is CAT062


def test_emergency_codes_cover_the_standard_range():
    emergencies = CAT062["I062/080"]["EMS"]
    assert emergencies[0] == "no emergency"
    assert emergencies[5] == "unlawful interference"
    assert set(emergencies) == set(range(7))
