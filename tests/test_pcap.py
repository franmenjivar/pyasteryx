import struct

from pyasteryx import Decoder
from pyasteryx.io.pcap import iter_pcap_payloads


def _build_udp_packet(payload: bytes) -> bytes:
    """Ethernet II + IPv4 + UDP frame wrapping ``payload`` (all network byte order)."""
    eth = bytes.fromhex("aabbccddeeff") + bytes.fromhex("112233445566") + struct.pack(">H", 0x0800)

    udp_len = 8 + len(payload)
    udp = struct.pack(">HHHH", 30001, 8600, udp_len, 0) + payload

    total_len = 20 + len(udp)
    ip = struct.pack(
        ">BBHHHBBH4s4s",
        0x45,  # version 4, IHL 5
        0x00,  # DSCP/ECN
        total_len,
        0,  # identification
        0,  # flags + fragment offset
        64,  # TTL
        17,  # protocol UDP
        0,  # checksum (ignored)
        bytes.fromhex("0a000001"),  # src 10.0.0.1
        bytes.fromhex("ef000001"),  # dst 239.0.0.1
    )
    return eth + ip + udp


def _build_pcap(payloads) -> bytes:
    # Little-endian classic pcap global header, linktype 1 (Ethernet).
    out = bytearray(
        struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1)
    )
    for payload in payloads:
        packet = _build_udp_packet(payload)
        out += struct.pack("<IIII", 0, 0, len(packet), len(packet))
        out += packet
    return bytes(out)


def test_iter_pcap_payloads_extracts_udp(tmp_path, cat021_block):
    path = tmp_path / "capture.pcap"
    path.write_bytes(_build_pcap([cat021_block]))
    payloads = list(iter_pcap_payloads(path))
    assert payloads == [cat021_block]


def test_decode_pcap_end_to_end(tmp_path, cat021_block):
    path = tmp_path / "capture.pcap"
    path.write_bytes(_build_pcap([cat021_block, cat021_block]))
    messages = Decoder().decode_pcap(path)
    assert len(messages) == 2
    assert messages[0]["I021/080"]["TAddr"] == "3C6DA9"
