"""Tests for the live UDP / multicast feed reader.

These bind real sockets on the loopback interface and send real datagrams, so
they exercise the actual socket setup rather than a mock of it. They use
ephemeral ports and a hard datagram cap so they always terminate.
"""

from __future__ import annotations

import socket
import threading

import pytest

from pyasteryx import Decoder
from pyasteryx.io.net import NetworkError, iter_udp, open_udp_socket


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _send_later(port: int, payloads, delay: float = 0.05) -> threading.Timer:
    """Send each payload to the loopback port shortly after the listener starts."""

    def _send():
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
            for payload in payloads:
                sender.sendto(payload, ("127.0.0.1", port))

    timer = threading.Timer(delay, _send)
    timer.daemon = True
    timer.start()
    return timer


class TestSocketSetup:
    def test_opens_and_binds_a_unicast_socket(self):
        port = _free_port()
        sock = open_udp_socket(port, bind="127.0.0.1", timeout=0.1)
        try:
            assert sock.getsockname()[1] == port
        finally:
            sock.close()

    def test_bad_multicast_group_raises_network_error(self):
        with pytest.raises(NetworkError, match="multicast"):
            open_udp_socket(_free_port(), group="1.2.3.4", iface="203.0.113.99", bind="127.0.0.1")

    def test_bad_bind_address_raises_network_error(self):
        with pytest.raises(NetworkError, match="Could not open UDP socket"):
            open_udp_socket(9999, bind="203.0.113.99")


class TestIterUdp:
    def test_yields_datagram_payloads_in_order(self):
        port = _free_port()
        _send_later(port, [b"one", b"two", b"three"])
        received = list(iter_udp(port, bind="127.0.0.1", timeout=2.0, max_datagrams=3))
        assert received == [b"one", b"two", b"three"]

    def test_stops_on_timeout_with_no_traffic(self):
        assert list(iter_udp(_free_port(), bind="127.0.0.1", timeout=0.05)) == []

    def test_max_datagrams_stops_early(self):
        port = _free_port()
        _send_later(port, [b"a", b"b", b"c"])
        assert list(iter_udp(port, bind="127.0.0.1", timeout=2.0, max_datagrams=2)) == [b"a", b"b"]

    def test_socket_is_closed_when_the_consumer_abandons_the_generator(self):
        port = _free_port()
        _send_later(port, [b"only"])
        feed = iter_udp(port, bind="127.0.0.1", timeout=2.0)
        assert next(feed) == b"only"
        feed.close()  # simulates `break` out of the for-loop
        # The port is free again, which it would not be if the socket leaked.
        rebound = open_udp_socket(port, bind="127.0.0.1", timeout=0.01, reuse_port=False)
        rebound.close()


class TestDecoderOverUdp:
    def test_decodes_asterix_from_a_live_socket(self, cat021_block):
        port = _free_port()
        _send_later(port, [cat021_block, cat021_block])
        decoder = Decoder(on_error="skip")
        messages = list(
            decoder.iter_udp(port, bind="127.0.0.1", timeout=2.0, max_datagrams=2)
        )
        assert len(messages) == 2
        assert all(m.category == 21 for m in messages)

    def test_one_datagram_can_carry_several_data_blocks(self, cat021_block):
        port = _free_port()
        _send_later(port, [cat021_block * 3])
        decoder = Decoder()
        messages = list(decoder.iter_udp(port, bind="127.0.0.1", timeout=2.0, max_datagrams=1))
        assert len(messages) == 3
