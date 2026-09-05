"""The parser layer: category-agnostic ASTERIX structure decoding.

This layer knows how to walk the *structure* of an ASTERIX stream — data-block
headers, FSPECs and the generic data-item encodings — but it holds no per-field
knowledge. What each item and field *means* comes from the specifications in
:mod:`pyasteryx.spec`. This separation is what will let the whole layer be swapped for
a Rust/PyO3 implementation later without touching the public API.
"""

from pyasteryx.parser.fspec import parse_fspec
from pyasteryx.parser.header import DataBlockHeader, parse_data_block_header
from pyasteryx.parser.record import parse_record

__all__ = [
    "DataBlockHeader",
    "parse_data_block_header",
    "parse_fspec",
    "parse_record",
]
