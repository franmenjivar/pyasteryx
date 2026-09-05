"""Record parsing: turn one ASTERIX record into a :class:`~pyasteryx.models.Message`.

A record is an FSPEC followed by the data items its presence bits select, in
User Application Profile (UAP) order. This module maps present FRNs to item ids
via the category's UAP, then delegates the actual octet decoding to
:mod:`pyasteryx.parser.items`.
"""

from __future__ import annotations

from pyasteryx.exceptions import UnsupportedItemError
from pyasteryx.models import Message
from pyasteryx.parser.fspec import parse_fspec
from pyasteryx.parser.items import decode_item
from pyasteryx.spec.model import CategorySpec


def parse_record(
    spec: CategorySpec, data: memoryview, offset: int, limit: int
) -> tuple[Message, int]:
    """Parse a single record starting at ``offset``.

    Args:
        spec: The category specification governing this record.
        data: Buffer containing the record.
        offset: Offset of the record's first octet (the start of its FSPEC).
        limit: Offset just past the end of the data block's records.

    Returns:
        ``(message, new_offset)`` where ``new_offset`` is the offset of the next
        record (or ``limit`` if this was the last one).

    Raises:
        UnsupportedItemError: If the FSPEC selects an item the spec does not
            define (its length is unknown, so decoding cannot continue).
        DecodeError: On any structural problem (truncation, bad FSPEC, ...).
    """
    frns, pos = parse_fspec(data, offset, limit)

    items = {}
    for frn in frns:
        item_id = spec.item_for_frn(frn)
        if item_id is None:
            raise UnsupportedItemError(spec.category, frn)

        item_spec = spec.items.get(item_id)
        if item_spec is None:  # pragma: no cover - guarded by loader validation
            raise UnsupportedItemError(spec.category, frn, item_id)

        value, pos = decode_item(item_spec, data, pos, limit)
        items[item_id] = value

    return Message(category=spec.category, items=items), pos
