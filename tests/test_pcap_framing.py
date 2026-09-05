"""Tests for the pcap link/network/transport walk.

The reader has to skip everything that is not Ethernet/IPv4/UDP without
desynchronising, and cope with both byte orders and both timestamp resolutions.
"""

from __future__ import annotations

import struct

import pytest

from pyasteryx import Decoder
from pyasteryx.io.pcap import PcapError, iter_pcap_payloads

_MAGIC_US_LE = 0xA1B2C3D4
_MAGIC_NS_LE = 0xA1B23C4D
_LINKTYPE_ETHERNET = 1
_LINKTYPE_RAW_IP = 101


def _global_header(endian: str, magic: int, linktype: int) -> bytes:
    return struct.pack(endian + "IHHiIII", magic, 2, 4, 0, 0, 65535, linktype)


def _packet(endian: str, frame: bytes) -> bytes:
    return struct.pack(endian + "IIII", 1757000000, 0, len(frame), len(frame)) + frame


def _ipv4(payload: bytes, protocol: int = 17, ihl_words: int = 5) -> bytes:
    ihl = ihl_words * 4
    header = struct.pack(
        ">BBHHHBBH4s4s", 0x40 | ihl_words, 0, ihl + len(payload), 0, 0, 64, protocol, 0,
        bytes([10, 0, 0, 1]), bytes([239, 1, 1, 1]),
    )
    return header + b"\x00" * (ihl - 20) + payload


def _udp(payload: bytes) -> bytes:
    return struct.pack(">HHHH", 40000, 8600, 8 + len(payload), 0) + payload


def _ethernet(payload: bytes, ethertype: int = 0x0800, vlans: int = 0) -> bytes:
    frame = b"\x01\x00\x5e\x01\x01\x01" + b"\xaa" * 6
    for _ in range(vlans):
        frame += struct.pack(">HH", 0x8100, 0x0064)
    return frame + struct.pack(">H", ethertype) + payload


def _write(tmp_path, frames, endian="<", magic=_MAGIC_US_LE, linktype=_LINKTYPE_ETHERNET):
    path = tmp_path / "c.pcap"
    path.write_bytes(
        _global_header(endian, magic, linktype) + b"".join(_packet(endian, f) for f in frames)
    )
    return path


class TestFileFormat:
    @pytest.mark.parametrize("endian", ["<", ">"])
    @pytest.mark.parametrize("magic", [_MAGIC_US_LE, _MAGIC_NS_LE])
    def test_reads_both_byte_orders_and_timestamp_resolutions(self, tmp_path, endian, magic):
        frame = _ethernet(_ipv4(_udp(b"PAYLOAD")))
        path = _write(tmp_path, [frame], endian=endian, magic=magic)
        assert list(iter_pcap_payloads(path)) == [b"PAYLOAD"]

    def test_rejects_a_non_pcap_file(self, tmp_path):
        path = tmp_path / "not.pcap"
        path.write_bytes(b"\x00" * 40)
        with pytest.raises(PcapError, match="Not a classic pcap file"):
            list(iter_pcap_payloads(path))

    def test_rejects_a_file_too_small_for_a_header(self, tmp_path):
        path = tmp_path / "tiny.pcap"
        path.write_bytes(b"\x00" * 8)
        with pytest.raises(PcapError, match="too small"):
            list(iter_pcap_payloads(path))

    def test_rejects_truncated_packet_data(self, tmp_path):
        path = tmp_path / "cut.pcap"
        path.write_bytes(
            _global_header("<", _MAGIC_US_LE, _LINKTYPE_ETHERNET)
            + struct.pack("<IIII", 0, 0, 100, 100)
            + b"\x00" * 10
        )
        with pytest.raises(PcapError, match="Truncated packet data"):
            list(iter_pcap_payloads(path))


class TestLinkLayer:
    def test_hops_over_vlan_tags(self, tmp_path):
        frame = _ethernet(_ipv4(_udp(b"VLAN")), vlans=2)
        assert list(iter_pcap_payloads(_write(tmp_path, [frame]))) == [b"VLAN"]

    def test_skips_non_ipv4_ethertypes(self, tmp_path):
        arp = _ethernet(b"\x00" * 40, ethertype=0x0806)
        good = _ethernet(_ipv4(_udp(b"KEEP")))
        assert list(iter_pcap_payloads(_write(tmp_path, [arp, good]))) == [b"KEEP"]

    def test_supports_raw_ip_captures_with_no_link_layer(self, tmp_path):
        path = _write(tmp_path, [_ipv4(_udp(b"RAW"))], linktype=_LINKTYPE_RAW_IP)
        assert list(iter_pcap_payloads(path)) == [b"RAW"]

    def test_skips_unknown_link_types(self, tmp_path):
        path = _write(tmp_path, [_ethernet(_ipv4(_udp(b"X")))], linktype=999)
        assert list(iter_pcap_payloads(path)) == []

    def test_skips_a_runt_frame(self, tmp_path):
        assert list(iter_pcap_payloads(_write(tmp_path, [b"\x00" * 6]))) == []


class TestNetworkLayer:
    def test_skips_non_udp_protocols(self, tmp_path):
        tcp = _ethernet(_ipv4(b"\x00" * 20, protocol=6))
        good = _ethernet(_ipv4(_udp(b"KEEP")))
        assert list(iter_pcap_payloads(_write(tmp_path, [tcp, good]))) == [b"KEEP"]

    def test_honours_ip_header_options(self, tmp_path):
        """A longer IHL must shift where the UDP header is read from."""
        frame = _ethernet(_ipv4(_udp(b"OPTIONS"), ihl_words=7))
        assert list(iter_pcap_payloads(_write(tmp_path, [frame]))) == [b"OPTIONS"]

    def test_skips_ipv6(self, tmp_path):
        frame = _ethernet(b"\x60" + b"\x00" * 39, ethertype=0x86DD)
        assert list(iter_pcap_payloads(_write(tmp_path, [frame]))) == []

    def test_skips_an_empty_udp_payload(self, tmp_path):
        assert list(iter_pcap_payloads(_write(tmp_path, [_ethernet(_ipv4(_udp(b"")))]))) == []


class TestDecodeOverPcap:
    def test_decodes_asterix_out_of_a_capture(self, tmp_path, cat062_block):
        frames = [_ethernet(_ipv4(_udp(cat062_block))) for _ in range(4)]
        messages = Decoder().decode_pcap(_write(tmp_path, frames))
        assert len(messages) == 4
        assert all(m.category == 62 for m in messages)

    def test_ignores_interleaved_noise(self, tmp_path, cat062_block):
        frames = [
            _ethernet(b"\x00" * 40, ethertype=0x0806),
            _ethernet(_ipv4(_udp(cat062_block))),
            _ethernet(_ipv4(b"\x00" * 20, protocol=1)),
            _ethernet(_ipv4(_udp(cat062_block))),
        ]
        assert len(Decoder().decode_pcap(_write(tmp_path, frames))) == 2
