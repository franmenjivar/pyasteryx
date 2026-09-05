"""ASTERIX data-block header parsing.

An ASTERIX data block starts with a 3-octet header::

    +--------+--------+--------+ ...
    |  CAT   |     LEN (2)     | records...
    +--------+--------+--------+

* ``CAT`` (1 octet) is the category number.
* ``LEN`` (2 octets, big-endian) is the total length of the data block in
  octets, *including* the 3 header octets.
"""

from __future__ import annotations

import struct
from typing import NamedTuple

from pyasteryx.exceptions import InvalidLengthError, TruncatedMessageError

HEADER_SIZE = 3

# Big-endian: unsigned byte (CAT) + unsigned short (LEN).
_HEADER = struct.Struct(">BH")


class DataBlockHeader(NamedTuple):
    """Parsed ASTERIX data-block header.

    Attributes:
        category: The category number (``CAT``).
        length: Total data-block length in octets, including the header.
        records_offset: Offset of the first record, relative to the block start.
        records_end: Offset just past the last record, relative to the block start.
    """

    category: int
    length: int
    records_offset: int
    records_end: int


def parse_data_block_header(data: memoryview, offset: int = 0) -> DataBlockHeader:
    """Parse the data-block header located at ``offset`` within ``data``.

    Args:
        data: The buffer containing one or more ASTERIX data blocks.
        offset: Offset of the data-block header within ``data``.

    Returns:
        The parsed :class:`DataBlockHeader`. The returned offsets are absolute
        within ``data`` (i.e. they already include ``offset``).

    Raises:
        TruncatedMessageError: If fewer than 3 octets remain for the header, or
            the declared length runs past the end of the buffer.
        InvalidLengthError: If the declared length is smaller than the header.
    """
    if offset + HEADER_SIZE > len(data):
        raise TruncatedMessageError(
            f"Need {HEADER_SIZE} octets for data-block header at offset {offset}, "
            f"only {len(data) - offset} available"
        )

    category, length = _HEADER.unpack_from(data, offset)

    if length < HEADER_SIZE:
        raise InvalidLengthError(
            f"Data block declares length {length}, which is smaller than the "
            f"{HEADER_SIZE}-octet header"
        )

    end = offset + length
    if end > len(data):
        raise TruncatedMessageError(
            f"Data block declares length {length} at offset {offset}, but only "
            f"{len(data) - offset} octets are available"
        )

    return DataBlockHeader(
        category=category,
        length=length,
        records_offset=offset + HEADER_SIZE,
        records_end=end,
    )
