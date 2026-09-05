"""Binary file and stream sources.

ASTERIX data blocks are self-delimiting: the 3-octet header carries the total
block length. That lets us frame a raw stream into individual data blocks
without ever buffering the whole thing, which is what
:func:`iter_stream_blocks` does.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import BinaryIO

from pyasteryx.exceptions import InvalidLengthError, TruncatedMessageError
from pyasteryx.parser.header import HEADER_SIZE

PathLike = str | Path


def read_bytes(path: PathLike) -> bytes:
    """Read an entire binary file into memory and return its bytes."""
    return Path(path).read_bytes()


def iter_stream_blocks(stream: BinaryIO) -> Iterator[bytes]:
    """Yield complete ASTERIX data blocks from a binary stream, one at a time.

    The stream is read incrementally: for each block only its header and body are
    pulled in, so multi-gigabyte captures stream through in constant memory.

    Args:
        stream: Any binary, readable file-like object.

    Yields:
        The raw bytes of each complete data block (header included).

    Raises:
        TruncatedMessageError: If the stream ends part-way through a block.
        InvalidLengthError: If a block declares a length smaller than its header.
    """
    while True:
        header = _read_exactly(stream, HEADER_SIZE)
        if not header:
            return  # Clean end of stream on a block boundary.
        if len(header) < HEADER_SIZE:
            raise TruncatedMessageError(
                f"Stream ended after {len(header)} octets while reading a data-block header"
            )

        length = (header[1] << 8) | header[2]
        if length < HEADER_SIZE:
            raise InvalidLengthError(
                f"Data block declares length {length}, smaller than the {HEADER_SIZE}-octet header"
            )

        body = _read_exactly(stream, length - HEADER_SIZE)
        if len(body) < length - HEADER_SIZE:
            raise TruncatedMessageError(
                f"Data block declares length {length} but the stream ended early"
            )

        yield header + body


def _read_exactly(stream: BinaryIO, count: int) -> bytes:
    """Read up to ``count`` bytes, retrying short reads until EOF."""
    if count == 0:
        return b""
    chunks = []
    remaining = count
    while remaining > 0:
        chunk = stream.read(remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)
