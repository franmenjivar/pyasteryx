import pytest

from pyasteryx.exceptions import InvalidLengthError, TruncatedMessageError
from pyasteryx.parser.fspec import parse_fspec
from pyasteryx.parser.header import parse_data_block_header


def _mv(hexstr):
    return memoryview(bytes.fromhex(hexstr))


def test_header_parses_category_and_length():
    header = parse_data_block_header(_mv("15 0018" + "00" * 21), 0)
    assert header.category == 21
    assert header.length == 24
    assert header.records_offset == 3
    assert header.records_end == 24


def test_header_rejects_length_below_header():
    with pytest.raises(InvalidLengthError):
        parse_data_block_header(_mv("15 0002"), 0)


def test_header_rejects_length_past_buffer():
    with pytest.raises(TruncatedMessageError):
        parse_data_block_header(_mv("15 00FF"), 0)


def test_fspec_single_octet():
    # 0xE5 = 1110 0101 -> FRN 1,2,3,6 present, FX=0 after clearing bit1... bit1=1.
    # Use 0xE4 = 1110 0100 -> FRN 1,2,3,6 present, FX=0.
    frns, new_offset = parse_fspec(_mv("E4"), 0, 1)
    assert frns == [1, 2, 3, 6]
    assert new_offset == 1


def test_fspec_multi_octet_extension():
    # E5 -> FRN 1,2,3,6 present + FX; 0A -> FRN of second octet 12,14, FX=0.
    # Second octet 0x0A = 0000 1010 -> bit4(FRN12), bit2(FRN14).
    data = _mv("E5 0A")
    frns, new_offset = parse_fspec(data, 0, 2)
    assert frns == [1, 2, 3, 6, 12, 14]
    assert new_offset == 2


def test_fspec_truncated_extension_raises():
    with pytest.raises(TruncatedMessageError):
        parse_fspec(_mv("E5"), 0, 1)  # FX set but no next octet within limit
