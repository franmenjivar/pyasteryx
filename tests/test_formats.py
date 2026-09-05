"""Exercise every data-item encoding through the full decode pipeline."""

from pyasteryx import Decoder, SpecRegistry
from pyasteryx.spec import category_from_dict
from tests.asterix_builder import build_block

_CATEGORY = {
    "category": 200,
    "edition": "1.0",
    "name": "Format test",
    "uap": ["I200/010", "I200/020", "I200/030", "I200/040"],
    "items": [
        {
            "id": "I200/010",
            "format": "repetitive",
            "length": 2,
            "fields": [{"name": "A", "from": 16, "to": 9}, {"name": "B", "from": 8, "to": 1}],
        },
        {"id": "I200/020", "format": "explicit"},
        {
            "id": "I200/030",
            "format": "extended",
            "parts": [{"length": 3, "fields": [{"name": "X", "from": 24, "to": 2}]}],
        },
        {
            "id": "I200/040",
            "format": "compound",
            "subfields": [
                {"id": "S1", "format": "fixed", "length": 1, "fields": [{"name": "V", "from": 8, "to": 1}]},
                {"id": "S2", "format": "fixed", "length": 2, "fields": [{"name": "W", "from": 16, "to": 1}]},
            ],
        },
    ],
}


def _decoder():
    return Decoder(registry=SpecRegistry([category_from_dict(_CATEGORY)]))


def test_repetitive():
    spec = category_from_dict(_CATEGORY)
    block = build_block(spec, {"I200/010": bytes.fromhex("02" "0102" "0304")})
    msg = _decoder().decode(block)[0]
    assert msg["I200/010"] == [{"A": 1, "B": 2}, {"A": 3, "B": 4}]


def test_explicit():
    spec = category_from_dict(_CATEGORY)
    block = build_block(spec, {"I200/020": bytes.fromhex("03" "AABB")})
    msg = _decoder().decode(block)[0]
    assert msg["I200/020"] == {"len": 3, "raw": "AABB"}


def test_extended_multi_octet_extent():
    spec = category_from_dict(_CATEGORY)
    # 3-octet extent 0x123456; FX bit is LSB (0) -> single extent. X = value >> 1.
    block = build_block(spec, {"I200/030": bytes.fromhex("123456")})
    msg = _decoder().decode(block)[0]
    assert msg["I200/030"] == {"X": 0x123456 >> 1}


def test_compound():
    spec = category_from_dict(_CATEGORY)
    # primary 0xC0 selects S1 and S2; then S1=0x05, S2=0x1234.
    block = build_block(spec, {"I200/040": bytes.fromhex("C0" "05" "1234")})
    msg = _decoder().decode(block)[0]
    assert msg["I200/040"] == {"S1": {"V": 5}, "S2": {"W": 0x1234}}
