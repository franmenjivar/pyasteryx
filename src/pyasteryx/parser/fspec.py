"""FSPEC (Field Specification) parsing.

The FSPEC is a variable-length bit field at the start of every ASTERIX record.
Each octet carries seven presence bits plus a "field extension" (FX) bit::

    bit:   8   7   6   5   4   3   2   1
          FRN FRN FRN FRN FRN FRN FRN  FX

* Bit 8 (MSB) of the first octet is FRN 1, bit 7 is FRN 2, ... bit 2 is FRN 7.
* Bit 1 (LSB, the FX bit) signals whether another FSPEC octet follows.
* The second octet continues with FRN 8..14, and so on.

A set presence bit means the corresponding data item is present in the record.
"""

from __future__ import annotations

from typing import List

from pyasteryx.exceptions import InvalidFspecError, TruncatedMessageError

# A sane cap: 7 FRNs per octet, so this allows well over a thousand items.
_MAX_FSPEC_OCTETS = 32


def parse_fspec(data: memoryview, offset: int, limit: int) -> tuple[List[int], int]:
    """Parse the FSPEC starting at ``offset``.

    Args:
        data: Buffer containing the record.
        offset: Offset of the first FSPEC octet.
        limit: Offset just past the end of the record; the FSPEC may not read
            beyond this.

    Returns:
        A ``(frns, new_offset)`` tuple, where ``frns`` is the sorted list of
        present Field Reference Numbers (1-indexed) and ``new_offset`` is the
        offset of the first data item, just past the FSPEC.

    Raises:
        TruncatedMessageError: If the FX bit requests another octet but the
            record has ended.
        InvalidFspecError: If the FSPEC does not terminate within a sane number
            of octets.
    """
    frns: List[int] = []
    pos = offset

    for octet_index in range(_MAX_FSPEC_OCTETS):
        if pos >= limit:
            raise TruncatedMessageError(
                f"FSPEC extends past the end of the record at offset {pos}"
            )

        octet = data[pos]
        pos += 1

        base = octet_index * 7
        # Bit 8 -> FRN base+1, bit 7 -> base+2, ... bit 2 -> base+7.
        for bit in range(7):
            if octet & (0x80 >> bit):
                frns.append(base + bit + 1)

        # Bit 1 (LSB) is the FX bit.
        if not (octet & 0x01):
            return frns, pos

    raise InvalidFspecError(
        f"FSPEC did not terminate within {_MAX_FSPEC_OCTETS} octets at offset {offset}"
    )
