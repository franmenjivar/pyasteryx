"""Tests for specification loading and the edition-aware registry."""

import pytest

from pyasteryx import Decoder
from pyasteryx.exceptions import SpecificationError, UnsupportedCategoryError


def test_bundled_categories_present(registry):
    cats = set(registry.categories())
    assert {21, 48, 62} <= cats


def test_bundled_editions(registry):
    assert registry.latest_edition(21) == "2.6"
    assert registry.latest_edition(48) == "1.21"
    assert registry.latest_edition(62) == "1.18"


def test_multiple_editions_loaded(registry):
    # Newest is used by default, but older editions remain selectable.
    assert {"2.4", "2.6"} <= set(registry.editions(21))
    assert registry.get(21, "2.4").edition == "2.4"
    assert registry.get(21).edition == "2.6"


def test_full_uap_coverage(registry):
    # Every FRN slot in these editions should resolve to a defined item.
    for cat in (21, 48, 62):
        spec = registry.get(cat)
        for frn, item_id in enumerate(spec.uap, start=1):
            if item_id is not None:
                assert item_id in spec.items, f"CAT{cat} FRN{frn} -> {item_id} undefined"


def test_get_unknown_category_raises(registry):
    with pytest.raises(UnsupportedCategoryError):
        registry.get(999)


def test_get_unknown_edition_raises(registry):
    with pytest.raises(SpecificationError):
        registry.get(21, "9.9")


def test_decoder_edition_selection(cat021_block):
    # Pinning the shipped edition explicitly must behave identically to the default.
    default = Decoder().decode(cat021_block)
    pinned = Decoder(editions={21: "2.6"}).decode(cat021_block)
    assert [m.items for m in default] == [m.items for m in pinned]
