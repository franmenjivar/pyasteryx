import io

import pytest

from pyasteryx import Message


def test_decode_single_record(decoder, cat021_block):
    messages = decoder.decode(cat021_block)
    assert len(messages) == 1
    assert isinstance(messages[0], Message)
    assert messages[0].category == 21


def test_fixed_item_fields(decoder, cat021_block):
    msg = decoder.decode(cat021_block)[0]
    assert msg["I021/010"] == {"SAC": 25, "SIC": 200}


def test_extended_item_single_extent(decoder, cat021_block):
    msg = decoder.decode(cat021_block)[0]
    assert msg["I021/040"] == {"ATP": 5, "ARC": 1, "RC": 1, "RAB": 0}


def test_signed_scaled_position(decoder, cat021_block):
    pos = decoder.decode(cat021_block)[0]["I021/130"]
    assert pos["Lat"] == pytest.approx(45.0, abs=1e-4)
    assert pos["Lon"] == pytest.approx(45.0, abs=1e-4)


def test_signed_scaled_height_and_fl(decoder, cat021_block):
    msg = decoder.decode(cat021_block)[0]
    assert msg["I021/140"]["geometric_height"] == pytest.approx(2000.0)
    assert msg["I021/145"]["FL"] == pytest.approx(350.0)


def test_hex_and_sixbit_encoding(decoder, cat021_block):
    msg = decoder.decode(cat021_block)[0]
    assert msg["I021/080"] == {"TAddr": "3C6DA9"}
    assert msg["I021/170"] == {"TId": "ABCD1234"}


def test_to_dict_flattens_fields(decoder, cat021_block):
    flat = decoder.decode(cat021_block)[0].to_dict()
    assert flat["category"] == 21
    assert flat["I021/010.SAC"] == 25
    assert flat["I021/080.TAddr"] == "3C6DA9"


def test_iter_matches_decode(decoder, cat021_block):
    from_iter = [m.items for m in decoder.iter_messages(cat021_block)]
    from_decode = [m.items for m in decoder.decode(cat021_block)]
    assert from_iter == from_decode


def test_multiple_concatenated_blocks(decoder, cat021_block):
    messages = decoder.decode(cat021_block + cat021_block)
    assert len(messages) == 2


def test_decode_file(tmp_path, decoder, cat021_block):
    path = tmp_path / "capture.bin"
    path.write_bytes(cat021_block)
    messages = decoder.decode_file(path)
    assert len(messages) == 1
    assert messages[0]["I021/010"]["SAC"] == 25


def test_decode_stream(decoder, cat021_block):
    stream = io.BytesIO(cat021_block + cat021_block)
    assert len(decoder.decode_stream(stream)) == 2
