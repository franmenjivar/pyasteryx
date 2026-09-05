"""Helpers to assemble valid ASTERIX byte streams for tests.

Building records from the *loaded* specification (rather than hand-writing FSPEC
octets) keeps the tests honest: the FSPEC is derived from each item's real FRN in
the real UAP, so a test exercises exactly the edition the library ships.
"""

from __future__ import annotations

from typing import Dict

from pyasteryx.spec.model import CategorySpec


def frn_map(spec: CategorySpec) -> Dict[str, int]:
    """Return a mapping of item id -> Field Reference Number for a category."""
    return {item_id: idx + 1 for idx, item_id in enumerate(spec.uap) if item_id}


def build_block(spec: CategorySpec, items: Dict[str, bytes]) -> bytes:
    """Assemble a one-record data block containing ``items`` (id -> raw octets).

    The FSPEC is computed from each item's FRN; items are laid out in UAP order.
    """
    fm = frn_map(spec)
    present = sorted((fm[item_id], item_id) for item_id in items)
    max_frn = present[-1][0]
    n_octets = (max_frn + 6) // 7

    octets = bytearray(n_octets)
    for frn, _ in present:
        octet_index = (frn - 1) // 7
        bit = (frn - 1) % 7
        octets[octet_index] |= 0x80 >> bit
    for i in range(n_octets - 1):  # set FX on every non-final FSPEC octet
        octets[i] |= 0x01

    body = b"".join(items[item_id] for _, item_id in present)
    record = bytes(octets) + body
    length = len(record) + 3
    return bytes([spec.category]) + length.to_bytes(2, "big") + record


def _char_to_sixbit(ch: str) -> int:
    if "A" <= ch <= "Z":
        return ord(ch) - ord("A") + 1
    if ch == " ":
        return 32
    if "0" <= ch <= "9":
        return ord(ch) - ord("0") + 48
    return 0


def encode_sixbit(text: str, n_chars: int) -> bytes:
    """Encode ``text`` as ``n_chars`` ASTERIX 6-bit characters (n_chars*6/8 octets)."""
    text = text.ljust(n_chars)[:n_chars]
    value = 0
    for ch in text:
        value = (value << 6) | _char_to_sixbit(ch)
    return value.to_bytes(n_chars * 6 // 8, "big")
