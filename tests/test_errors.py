import pytest

from pyasteryx import Decoder, SpecRegistry
from pyasteryx.decoder import ON_ERROR_SKIP
from pyasteryx.exceptions import (
    TruncatedMessageError,
    UnsupportedCategoryError,
    UnsupportedItemError,
)
from pyasteryx.spec import category_from_dict
from tests.asterix_builder import build_block

# A tiny custom category with a deliberate gap (null) at FRN 2.
_GAP_CATEGORY = {
    "category": 200,
    "edition": "1.0",
    "name": "Gap test",
    "uap": ["I200/010", None, "I200/030"],
    "items": [
        {"id": "I200/010", "format": "fixed", "length": 1, "fields": [{"name": "A", "from": 8, "to": 1}]},
        {"id": "I200/030", "format": "fixed", "length": 1, "fields": [{"name": "C", "from": 8, "to": 1}]},
    ],
}


def test_unsupported_category_raises():
    block = bytes.fromhex("63 0004 00")  # CAT099, LEN=4
    with pytest.raises(UnsupportedCategoryError) as exc:
        Decoder().decode(block)
    assert exc.value.category == 99


def test_unsupported_item_raises():
    spec = category_from_dict(_GAP_CATEGORY)
    decoder = Decoder(registry=SpecRegistry([spec]))
    # FSPEC selecting FRN 2 (the null slot): bit7 set -> 0x40, FX=0.
    block = bytes.fromhex("C8 0004 40")
    with pytest.raises(UnsupportedItemError) as exc:
        decoder.decode(block)
    assert exc.value.frn == 2


def test_truncated_block_raises():
    block = bytes.fromhex("15 0018 E5")  # declares LEN=24, only 4 octets present
    with pytest.raises(TruncatedMessageError):
        Decoder().decode(block)


def test_on_error_skip_swallows_bad_block():
    decoder = Decoder(on_error=ON_ERROR_SKIP)
    assert decoder.decode(bytes.fromhex("63 0004 00")) == []


def test_invalid_on_error_rejected():
    with pytest.raises(ValueError):
        Decoder(on_error="explode")


def test_gap_category_decodes_defined_items():
    spec = category_from_dict(_GAP_CATEGORY)
    decoder = Decoder(registry=SpecRegistry([spec]))
    block = build_block(spec, {"I200/010": b"\x2a", "I200/030": b"\x07"})
    msg = decoder.decode(block)[0]
    assert msg["I200/010"] == {"A": 42}
    assert msg["I200/030"] == {"C": 7}
