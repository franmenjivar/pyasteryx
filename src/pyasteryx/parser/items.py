"""Generic, specification-driven data-item decoding.

These functions decode every ASTERIX data-item encoding — fixed, extended,
repetitive, compound and explicit — using only the
:class:`~pyasteryx.spec.model.ItemSpec` that describes them. No field meaning is
hardcoded here.

Performance notes:
* Item octets are read through ``memoryview`` slices (no intermediate ``bytes``
  copies) and turned into a single big-endian integer with ``int.from_bytes``.
* Field extraction is pure integer shifting/masking — no per-field allocation
  beyond the resulting value.
"""

from __future__ import annotations

from typing import Any

from pyasteryx.exceptions import InvalidLengthError, TruncatedMessageError
from pyasteryx.spec.model import (
    COMPOUND,
    EXPLICIT,
    EXTENDED,
    FIXED,
    REPETITIVE,
    FieldSpec,
    ItemSpec,
)


def _sixbit_char(value: int) -> str:
    """Map one 6-bit code to its ASTERIX/IA5 character."""
    if 1 <= value <= 26:
        return chr(ord("A") + value - 1)
    if value == 32:
        return " "
    if 48 <= value <= 57:
        return chr(ord("0") + value - 48)
    return ""  # unused code points


def _decode_sixbit(value: int, width: int) -> str:
    """Decode ``width`` bits (a multiple of 6) as ASTERIX 6-bit characters."""
    chars = []
    for i in range(width // 6):
        shift = width - 6 * (i + 1)
        chars.append(_sixbit_char((value >> shift) & 0x3F))
    return "".join(chars).rstrip()


def _extract_fields(fields: tuple[FieldSpec, ...], raw: int, out: dict[str, Any]) -> None:
    """Extract each field from ``raw`` (big-endian integer) into ``out``."""
    for f in fields:
        width = f.bit_from - f.bit_to + 1
        value: Any = (raw >> (f.bit_to - 1)) & ((1 << width) - 1)

        encode = f.encode
        if encode == "ascii":
            out[f.name] = value.to_bytes(width // 8, "big").decode("ascii", "replace").rstrip()
            continue
        if encode == "6bitschar":
            out[f.name] = _decode_sixbit(value, width)
            continue

        if f.signed and value >= (1 << (width - 1)):
            value -= 1 << width

        if f.scale is not None:
            value = value * f.scale
        elif encode == "hex":
            value = format(value, f"0{(width + 3) // 4}X")
        elif encode == "octal":
            value = format(value, f"0{(width + 2) // 3}o")

        out[f.name] = value


def _decode_fixed(
    item: ItemSpec, data: memoryview, offset: int, limit: int
) -> tuple[dict[str, Any], int]:
    end = offset + item.length
    if end > limit:
        raise TruncatedMessageError(
            f"Item {item.item_id} needs {item.length} octets at offset {offset}, "
            f"only {limit - offset} available"
        )
    raw = int.from_bytes(data[offset:end], "big")
    out: dict[str, Any] = {}
    _extract_fields(item.fields, raw, out)
    return out, end


def _decode_extended(
    item: ItemSpec, data: memoryview, offset: int, limit: int
) -> tuple[dict[str, Any], int]:
    out: dict[str, Any] = {}
    parts = item.parts
    n = len(parts)
    pos = offset
    index = 0

    while True:
        # Beyond the defined extents, reuse the last one (repeating extension).
        part = parts[index] if index < n else parts[-1]
        end = pos + part.length
        if end > limit:
            raise TruncatedMessageError(
                f"Extended item {item.item_id} runs past the end of the record at offset {pos}"
            )
        raw = int.from_bytes(data[pos:end], "big")
        _extract_fields(part.fields, raw, out)
        pos = end

        if not (raw & 0x01):  # FX bit is the LSB of the extent's last octet.
            break
        index += 1

    return out, pos


def _decode_repetitive(
    item: ItemSpec, data: memoryview, offset: int, limit: int
) -> tuple[list[dict[str, Any]], int]:
    if offset >= limit:
        raise TruncatedMessageError(
            f"Repetitive item {item.item_id} has no REP octet at offset {offset}"
        )
    rep = data[offset]
    pos = offset + 1
    blocks: list[dict[str, Any]] = []

    for _ in range(rep):
        end = pos + item.length
        if end > limit:
            raise TruncatedMessageError(
                f"Repetitive item {item.item_id} truncated: need {item.length} octets "
                f"at offset {pos}, only {limit - pos} available"
            )
        raw = int.from_bytes(data[pos:end], "big")
        block: dict[str, Any] = {}
        _extract_fields(item.fields, raw, block)
        blocks.append(block)
        pos = end

    return blocks, pos


def _decode_compound(
    item: ItemSpec, data: memoryview, offset: int, limit: int
) -> tuple[dict[str, Any], int]:
    # Primary subfield: an extended-style bitmap selecting which subfields follow.
    subfields = item.subfields
    present: list[bool] = []
    pos = offset

    while True:
        if pos >= limit:
            raise TruncatedMessageError(
                f"Compound item {item.item_id} primary subfield runs past the record end"
            )
        octet = data[pos]
        pos += 1
        for bit in range(7):  # bits 8..2 -> subfields in order
            present.append(bool(octet & (0x80 >> bit)))
        if not (octet & 0x01):
            break

    out: dict[str, Any] = {}
    for index, is_present in enumerate(present):
        if not is_present:
            continue
        if index >= len(subfields):
            raise TruncatedMessageError(
                f"Compound item {item.item_id}: primary subfield selects subfield "
                f"{index + 1}, which is not defined"
            )
        sub = subfields[index]
        value, pos = decode_item(sub, data, pos, limit)
        out[sub.item_id] = value

    return out, pos


def _decode_explicit(
    item: ItemSpec, data: memoryview, offset: int, limit: int
) -> tuple[dict[str, Any], int]:
    # Length-prefixed opaque block: first octet is the total length (inclusive).
    if offset >= limit:
        raise TruncatedMessageError(
            f"Explicit item {item.item_id} has no length octet at offset {offset}"
        )
    length = data[offset]
    if length < 1:
        raise InvalidLengthError(f"Explicit item {item.item_id} declares length {length}")
    end = offset + length
    if end > limit:
        raise TruncatedMessageError(
            f"Explicit item {item.item_id} declares length {length} but the record is shorter"
        )
    content = bytes(data[offset + 1 : end])
    return {"len": length, "raw": content.hex().upper()}, end


_DISPATCH = {
    FIXED: _decode_fixed,
    EXTENDED: _decode_extended,
    REPETITIVE: _decode_repetitive,
    COMPOUND: _decode_compound,
    EXPLICIT: _decode_explicit,
}


def decode_item(item: ItemSpec, data: memoryview, offset: int, limit: int) -> tuple[Any, int]:
    """Decode one data item, returning ``(value, new_offset)``.

    Args:
        item: The item specification.
        data: Buffer containing the record.
        offset: Offset of the item's first octet.
        limit: Offset just past the end of the record.

    Returns:
        ``(value, new_offset)`` where ``value`` is a dict of fields (or a list of
        dicts for repetitive items) and ``new_offset`` is the offset just past
        the item.
    """
    return _DISPATCH[item.fmt](item, data, offset, limit)
