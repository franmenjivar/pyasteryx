"""Native PCAP reader.

Parses classic ``.pcap`` files and yields the UDP payloads that carry ASTERIX,
transparently walking Ethernet -> IPv4 -> UDP so callers never touch raw packet
framing. Only the classic pcap format and Ethernet/IPv4/UDP are handled today;
``.pcapng`` and additional link/transport layers are planned.

The file is streamed packet-by-packet, so captures far larger than RAM decode
fine.
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import BinaryIO, Iterator, Union

from pyasteryx.exceptions import AsteryxError

PathLike = Union[str, Path]

# pcap global-header magic numbers, as read big-endian from the first 4 octets.
# The canonical value is 0xA1B2C3D4; a byte-swapped value means the writer used
# the opposite endianness, so the rest of the file must be read that way too.
_MAGIC_BE = 0xA1B2C3D4  # microsecond timestamps, big-endian file
_MAGIC_BE_SWAPPED = 0xD4C3B2A1  # microsecond timestamps, little-endian file
_MAGIC_NS_BE = 0xA1B23C4D  # nanosecond timestamps, big-endian file
_MAGIC_NS_SWAPPED = 0x4D3CB2A1  # nanosecond timestamps, little-endian file

_GLOBAL_HEADER_SIZE = 24
_PACKET_HEADER_SIZE = 16

_LINKTYPE_ETHERNET = 1
_LINKTYPE_RAW_IP_VALUES = (12, 101)  # raw IPv4/IPv6, no link layer

_ETHERTYPE_IPV4 = 0x0800
_ETHERTYPE_VLAN = 0x8100
_IP_PROTO_UDP = 17


class PcapError(AsteryxError):
    """Raised when a PCAP file cannot be parsed."""


def iter_pcap_payloads(path: PathLike) -> Iterator[bytes]:
    """Yield the UDP payload of every UDP packet in a classic pcap file.

    Non-IPv4 or non-UDP packets are skipped. Each yielded payload is the raw
    application data (the ASTERIX bytes), ready to hand to the decoder.

    Args:
        path: Path to a ``.pcap`` file.

    Yields:
        The UDP payload bytes of each UDP packet, in capture order.

    Raises:
        PcapError: If the file is not a recognisable classic pcap file.
    """
    with open(path, "rb") as fh:
        endian, linktype = _read_global_header(fh)
        rec_header = struct.Struct(endian + "IIII")

        while True:
            raw_header = fh.read(_PACKET_HEADER_SIZE)
            if not raw_header:
                return
            if len(raw_header) < _PACKET_HEADER_SIZE:
                raise PcapError("Truncated packet record header")

            _ts_sec, _ts_frac, incl_len, _orig_len = rec_header.unpack(raw_header)
            packet = fh.read(incl_len)
            if len(packet) < incl_len:
                raise PcapError("Truncated packet data")

            payload = _extract_udp_payload(memoryview(packet), linktype)
            if payload is not None:
                yield bytes(payload)


def _read_global_header(fh: BinaryIO) -> tuple[str, int]:
    """Read the pcap global header; return (struct endian char, linktype)."""
    header = fh.read(_GLOBAL_HEADER_SIZE)
    if len(header) < _GLOBAL_HEADER_SIZE:
        raise PcapError("File is too small to be a pcap file")

    magic = struct.unpack(">I", header[:4])[0]
    if magic in (_MAGIC_BE, _MAGIC_NS_BE):
        endian = ">"
    elif magic in (_MAGIC_BE_SWAPPED, _MAGIC_NS_SWAPPED):
        endian = "<"
    else:
        raise PcapError(
            f"Not a classic pcap file (unexpected magic 0x{magic:08X}); "
            f".pcapng is not yet supported"
        )

    # network/linktype is the last 4 octets of the global header.
    linktype = struct.unpack(endian + "I", header[20:24])[0]
    return endian, linktype


def _extract_udp_payload(packet: memoryview, linktype: int) -> memoryview | None:
    """Walk the link/network/transport layers and return the UDP payload."""
    if linktype == _LINKTYPE_ETHERNET:
        ip_offset = _strip_ethernet(packet)
        if ip_offset is None:
            return None
    elif linktype in _LINKTYPE_RAW_IP_VALUES:
        ip_offset = 0
    else:
        return None

    return _extract_udp_from_ip(packet, ip_offset)


def _strip_ethernet(packet: memoryview) -> int | None:
    """Return the offset of the IPv4 header after the Ethernet header, or None."""
    if len(packet) < 14:
        return None
    ethertype = (packet[12] << 8) | packet[13]
    offset = 14
    # Hop over any 802.1Q VLAN tags.
    while ethertype == _ETHERTYPE_VLAN:
        if len(packet) < offset + 4:
            return None
        ethertype = (packet[offset + 2] << 8) | packet[offset + 3]
        offset += 4
    if ethertype != _ETHERTYPE_IPV4:
        return None
    return offset


def _extract_udp_from_ip(packet: memoryview, ip_offset: int) -> memoryview | None:
    """Return the UDP payload from an IPv4 packet, or None if not IPv4/UDP."""
    if len(packet) < ip_offset + 20:
        return None

    version_ihl = packet[ip_offset]
    if (version_ihl >> 4) != 4:  # IPv4 only for now.
        return None
    ihl = (version_ihl & 0x0F) * 4
    if ihl < 20:
        return None

    protocol = packet[ip_offset + 9]
    if protocol != _IP_PROTO_UDP:
        return None

    total_length = (packet[ip_offset + 2] << 8) | packet[ip_offset + 3]
    udp_offset = ip_offset + ihl
    if len(packet) < udp_offset + 8:
        return None

    # UDP length covers header + payload; trust it but clamp to what we captured.
    udp_length = (packet[udp_offset + 4] << 8) | packet[udp_offset + 5]
    ip_end = ip_offset + total_length if total_length else len(packet)
    payload_start = udp_offset + 8
    payload_end = udp_offset + udp_length if udp_length >= 8 else ip_end
    payload_end = min(payload_end, ip_end, len(packet))
    if payload_end <= payload_start:
        return None

    return packet[payload_start:payload_end]
