"""The public decoding API.

:class:`Decoder` is the single entry point most users need. Every source has a
matching pair of methods:

* ``decode*`` -> eagerly returns a ``list[Message]``.
* ``iter_*`` -> lazily yields ``Message`` objects, so large files, pcaps and
  streams flow through in constant memory.

All the heavy lifting lives in the :mod:`pyasteryx.io`, :mod:`pyasteryx.parser` and
:mod:`pyasteryx.spec` layers; this class just wires them together. That is deliberate:
the public surface here is the contract we promise to keep stable even after the
parser is reimplemented in Rust.
"""

from __future__ import annotations

from pathlib import Path
from typing import BinaryIO, Dict, Generator, Iterator, List, Optional, Union

from pyasteryx.exceptions import DecodeError
from pyasteryx.io.binary import iter_stream_blocks
from pyasteryx.io.net import iter_multicast, iter_udp
from pyasteryx.io.pcap import iter_pcap_payloads
from pyasteryx.models import Message
from pyasteryx.parser.header import parse_data_block_header
from pyasteryx.parser.record import parse_record
from pyasteryx.spec import SpecRegistry

PathLike = Union[str, Path]

# How to react to a malformed data block.
ON_ERROR_RAISE = "raise"
ON_ERROR_SKIP = "skip"


class Decoder:
    """Decodes ASTERIX from raw bytes, files, streams and pcap captures.

    Args:
        registry: The set of category specifications to decode against. Defaults
            to every category and edition bundled with pyasteryx.
        editions: Optional mapping of category number -> edition string, selecting
            which edition to decode each category with (e.g. ``{62: "1.18"}``).
            Categories not listed use the newest loaded edition. The ASTERIX wire
            format does not carry the edition, so this is how you pin it.
        on_error: ``"raise"`` (default) to propagate a :class:`DecodeError` on the
            first malformed data block, or ``"skip"`` to drop the offending block
            and continue with the next one.
    """

    __slots__ = ("_registry", "_on_error", "_editions", "_errors")

    def __init__(
        self,
        registry: Optional[SpecRegistry] = None,
        editions: Optional[Dict[int, str]] = None,
        on_error: str = ON_ERROR_RAISE,
    ) -> None:
        if on_error not in (ON_ERROR_RAISE, ON_ERROR_SKIP):
            raise ValueError(f"on_error must be {ON_ERROR_RAISE!r} or {ON_ERROR_SKIP!r}")
        self._registry = registry if registry is not None else SpecRegistry.with_bundled()
        self._editions: Dict[int, str] = dict(editions) if editions else {}
        self._on_error = on_error
        self._errors = 0

    @property
    def registry(self) -> SpecRegistry:
        """The specification registry this decoder decodes against."""
        return self._registry

    @property
    def errors(self) -> int:
        """Number of data blocks skipped so far under ``on_error="skip"``.

        Always ``0`` when ``on_error="raise"``. Check it after a run to find out
        whether a feed or capture was clean.
        """
        return self._errors

    # -- Raw bytes ---------------------------------------------------------

    def iter_messages(self, raw: Union[bytes, bytearray, memoryview]) -> Iterator[Message]:
        """Lazily yield every record from a buffer of one or more data blocks."""
        data = memoryview(raw)
        offset = 0
        end = len(data)
        while offset < end:
            offset = yield from self._iter_data_block(data, offset)

    def decode(self, raw: Union[bytes, bytearray, memoryview]) -> List[Message]:
        """Eagerly decode every record from a buffer of one or more data blocks."""
        return list(self.iter_messages(raw))

    # -- Binary files ------------------------------------------------------

    def iter_file(self, path: PathLike) -> Iterator[Message]:
        """Lazily yield records from a binary ASTERIX file, streaming block by block."""
        with open(path, "rb") as fh:
            yield from self.iter_stream(fh)

    def decode_file(self, path: PathLike) -> List[Message]:
        """Eagerly decode every record from a binary ASTERIX file."""
        return list(self.iter_file(path))

    # -- File-like streams -------------------------------------------------

    def iter_stream(self, stream: BinaryIO) -> Iterator[Message]:
        """Lazily yield records from a binary, readable file-like stream."""
        blocks = iter_stream_blocks(stream)
        while True:
            try:
                block = next(blocks)
            except StopIteration:
                return
            except DecodeError:
                # Framing failed, so the rest of the stream cannot be located.
                # A capture cut mid-block is the common cause; under "skip" we
                # keep whatever was decoded up to here.
                if self._on_error == ON_ERROR_RAISE:
                    raise
                return
            # Each framed block is exactly one data block; the return offset is
            # its end, which we don't need here.
            yield from self._iter_data_block(memoryview(block), 0)

    def decode_stream(self, stream: BinaryIO) -> List[Message]:
        """Eagerly decode every record from a binary, readable file-like stream."""
        return list(self.iter_stream(stream))

    # -- PCAP --------------------------------------------------------------

    def iter_pcap(self, path: PathLike) -> Iterator[Message]:
        """Lazily yield records from a pcap capture (Ethernet/IPv4/UDP -> ASTERIX)."""
        for payload in iter_pcap_payloads(path):
            yield from self.iter_messages(payload)

    def decode_pcap(self, path: PathLike) -> List[Message]:
        """Eagerly decode every record from a pcap capture."""
        return list(self.iter_pcap(path))

    # -- Live network feeds ------------------------------------------------

    def iter_udp(
        self,
        port: int,
        group: Optional[str] = None,
        iface: str = "0.0.0.0",
        bind: str = "",
        timeout: Optional[float] = None,
        max_datagrams: Optional[int] = None,
    ) -> Iterator[Message]:
        """Lazily yield records from a live UDP feed, unicast or multicast.

        Each datagram carries whole data blocks, so records appear as soon as
        their datagram arrives. Consider ``on_error="skip"`` for a live feed: a
        single corrupt datagram should not end the session.

        Args:
            port: UDP port to listen on.
            group: Multicast group to join (e.g. ``"239.1.1.1"``), or ``None``
                for unicast.
            iface: Local interface address for the multicast join. Set this on a
                multi-homed host.
            bind: Local bind address; see :func:`pyasteryx.io.net.open_udp_socket`.
            timeout: Seconds to wait for a datagram before stopping. ``None``
                listens forever.
            max_datagrams: Stop after this many datagrams.

        Yields:
            Decoded records, indefinitely, in arrival order.
        """
        for payload in iter_udp(
            port,
            group=group,
            bind=bind,
            iface=iface,
            timeout=timeout,
            max_datagrams=max_datagrams,
        ):
            yield from self.iter_messages(payload)

    def iter_multicast(
        self,
        group: str,
        port: int,
        iface: str = "0.0.0.0",
        timeout: Optional[float] = None,
        max_datagrams: Optional[int] = None,
    ) -> Iterator[Message]:
        """Lazily yield records from an IP multicast feed.

        Args:
            group: Multicast group address (e.g. ``"239.1.1.1"``).
            port: UDP port.
            iface: Local interface address to join on.
            timeout: Seconds to wait for a datagram before stopping.
            max_datagrams: Stop after this many datagrams.

        Yields:
            Decoded records, indefinitely, in arrival order.
        """
        for payload in iter_multicast(
            group, port, iface=iface, timeout=timeout, max_datagrams=max_datagrams
        ):
            yield from self.iter_messages(payload)

    # -- Internals ---------------------------------------------------------

    def _iter_data_block(self, data: memoryview, offset: int) -> Generator[Message, None, int]:
        """Yield the records of the data block at ``offset``; return the next offset.

        Implemented as a generator whose ``return`` value (via ``StopIteration``)
        is the offset of the following data block, so ``iter_messages`` can walk
        a multi-block buffer with ``offset = yield from ...``.
        """
        try:
            header = parse_data_block_header(data, offset)
        except DecodeError:
            if self._on_error == ON_ERROR_RAISE:
                raise
            # Without a valid header the next block's offset is unknowable, so
            # walking on would only desynchronise. Abandon the rest of the buffer.
            return len(data)

        try:
            spec = self._registry.get(header.category, self._editions.get(header.category))
            pos = header.records_offset
            while pos < header.records_end:
                message, pos = parse_record(spec, data, pos, header.records_end)
                yield message
        except DecodeError:
            if self._on_error == ON_ERROR_RAISE:
                raise
            # The header framed this block correctly, so its declared length is
            # trustworthy even though its contents are not: skip just this block
            # and resume at the next one. An unsupported category lands here too.
            self._errors += 1
            return header.records_end
        return header.records_end
