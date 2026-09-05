"""The I/O layer: byte sources that feed the decoder.

Everything here yields raw ASTERIX bytes and is deliberately unaware of category
semantics. Sources are streaming-first: they hand the decoder one data block (or
one UDP payload) at a time so that arbitrarily large captures never need to be
held in memory at once.
"""

from pyasteryx.io.binary import iter_stream_blocks, read_bytes
from pyasteryx.io.pcap import iter_pcap_payloads

__all__ = [
    "iter_pcap_payloads",
    "iter_stream_blocks",
    "read_bytes",
]
