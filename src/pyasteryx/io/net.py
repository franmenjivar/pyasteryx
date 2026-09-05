"""Live network sources: UDP unicast and IP multicast.

CAT062 system-track data is almost always distributed as UDP — a tracker or
ARTAS server publishes to a multicast group that every downstream consumer
joins. This module turns such a feed into a plain Python iterator of datagram
payloads.

One datagram carries one or more complete ASTERIX data blocks, never a partial
one, so no reassembly is needed: each payload can go straight to the decoder.

Everything here is stdlib ``socket``; there is no extra dependency, and the
sockets are always closed, including when the consumer abandons the generator.
"""

from __future__ import annotations

import errno
import socket
import struct
from collections.abc import Iterator

from pyasteryx.exceptions import AsteryxError

__all__ = ["NetworkError", "iter_udp", "iter_multicast", "open_udp_socket"]

# Comfortably above the 65507-octet maximum UDP payload, so a datagram is never
# silently truncated.
_MAX_DATAGRAM = 65536

_DEFAULT_RECV_BUFFER = 4 * 1024 * 1024


class NetworkError(AsteryxError):
    """Raised when a feed socket cannot be opened or joined."""


def open_udp_socket(
    port: int,
    group: str | None = None,
    bind: str = "",
    iface: str = "0.0.0.0",
    timeout: float | None = None,
    recv_buffer: int = _DEFAULT_RECV_BUFFER,
    reuse_port: bool = True,
) -> socket.socket:
    """Create and bind a UDP socket, joining a multicast group if given.

    Args:
        port: UDP port to bind.
        group: Multicast group to join (e.g. ``"239.1.1.1"``). ``None`` for
            plain unicast.
        bind: Local address to bind to. Defaults to all interfaces. On Linux,
            binding to the group address filters out traffic for other groups on
            the same port; on macOS/BSD you must leave this empty.
        iface: Local interface address to receive the multicast on. Set this on
            a multi-homed host, otherwise the OS picks the default route, which
            is usually not the operational network.
        timeout: Socket timeout in seconds. ``None`` blocks indefinitely.
        recv_buffer: ``SO_RCVBUF`` size. A busy CAT062 feed will drop datagrams
            in the kernel with the default buffer, and the loss is silent.
        reuse_port: Also set ``SO_REUSEPORT`` where available, so several
            processes can consume the same feed.

    Returns:
        A bound, ready-to-receive socket. The caller owns it and must close it.

    Raises:
        NetworkError: If the socket cannot be created, bound, or joined.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if reuse_port and hasattr(socket, "SO_REUSEPORT"):
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except OSError:  # pragma: no cover - platform dependent
                pass
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, recv_buffer)
        except OSError:  # pragma: no cover - the kernel may cap this
            pass

        sock.bind((bind, port))

        if group is not None:
            try:
                membership = struct.pack(
                    "4s4s", socket.inet_aton(group), socket.inet_aton(iface)
                )
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
            except OSError as exc:
                raise NetworkError(
                    f"Could not join multicast group {group} on interface {iface}: {exc}"
                ) from exc

        sock.settimeout(timeout)
        return sock
    except NetworkError:
        sock.close()
        raise
    except OSError as exc:
        sock.close()
        raise NetworkError(f"Could not open UDP socket on {bind or '*'}:{port}: {exc}") from exc


def iter_udp(
    port: int,
    group: str | None = None,
    bind: str = "",
    iface: str = "0.0.0.0",
    timeout: float | None = None,
    max_datagrams: int | None = None,
    recv_buffer: int = _DEFAULT_RECV_BUFFER,
) -> Iterator[bytes]:
    """Yield the payload of every datagram arriving on a UDP feed.

    Runs until the consumer stops iterating, ``max_datagrams`` payloads have been
    yielded, or the socket times out. The socket is closed on every exit path,
    including ``break`` and exceptions.

    Args:
        port: UDP port to listen on.
        group: Multicast group to join, or ``None`` for unicast.
        bind: Local bind address; see :func:`open_udp_socket`.
        iface: Local interface for the multicast join.
        timeout: Seconds to wait for a datagram before stopping. ``None``
            (default) listens forever.
        max_datagrams: Stop after this many datagrams. Useful for sampling a
            feed or for tests.
        recv_buffer: Kernel receive buffer size; raise it on busy feeds.

    Yields:
        The payload bytes of each datagram, in arrival order.

    Raises:
        NetworkError: If the socket cannot be opened or joined.

    Example::

        from pyasteryx import Decoder
        from pyasteryx.io.net import iter_udp

        decoder = Decoder(on_error="skip")
        for payload in iter_udp(8600, group="239.1.1.1"):
            for msg in decoder.iter_messages(payload):
                ...
    """
    sock = open_udp_socket(
        port, group=group, bind=bind, iface=iface, timeout=timeout, recv_buffer=recv_buffer
    )
    count = 0
    try:
        while max_datagrams is None or count < max_datagrams:
            try:
                payload = sock.recv(_MAX_DATAGRAM)
            except TimeoutError:
                return
            except OSError as exc:
                if exc.errno in (errno.EBADF, errno.EINTR):
                    return
                raise NetworkError(f"Error receiving from the feed: {exc}") from exc
            if payload:
                count += 1
                yield payload
    finally:
        sock.close()


def iter_multicast(
    group: str,
    port: int,
    iface: str = "0.0.0.0",
    timeout: float | None = None,
    max_datagrams: int | None = None,
    recv_buffer: int = _DEFAULT_RECV_BUFFER,
) -> Iterator[bytes]:
    """Yield datagram payloads from an IP multicast feed.

    A thin, more readable wrapper over :func:`iter_udp` with ``group`` required
    and given first, matching how multicast feeds are written down
    (``239.1.1.1:8600``).

    Args:
        group: Multicast group address (e.g. ``"239.1.1.1"``).
        port: UDP port.
        iface: Local interface address to join on. Set this on multi-homed hosts.
        timeout: Seconds to wait for a datagram before stopping.
        max_datagrams: Stop after this many datagrams.
        recv_buffer: Kernel receive buffer size.

    Yields:
        The payload bytes of each datagram, in arrival order.
    """
    return iter_udp(
        port,
        group=group,
        iface=iface,
        timeout=timeout,
        max_datagrams=max_datagrams,
        recv_buffer=recv_buffer,
    )
