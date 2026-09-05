"""Tests for error recovery under ``on_error="skip"``.

A live feed or a field recording will contain the occasional bad block. The
question these tests pin down is exactly how much the decoder throws away when
it hits one: a block whose *header* framed correctly can be skipped precisely,
because its declared length still says where the next block starts.
"""

from __future__ import annotations

import io

import pytest

from pyasteryx import Decoder
from pyasteryx.exceptions import TruncatedMessageError, UnsupportedCategoryError


def _block(category: int, body: bytes) -> bytes:
    """Frame ``body`` as a data block of ``category`` with a correct length."""
    return bytes([category]) + (len(body) + 3).to_bytes(2, "big") + body


class TestSkipUnsupportedCategory:
    def test_raise_mode_propagates(self, cat021_block):
        decoder = Decoder()
        with pytest.raises(UnsupportedCategoryError):
            decoder.decode(cat021_block + _block(99, b"\x00\x00"))

    def test_skip_mode_resumes_at_the_next_block(self, cat021_block):
        """The bad block's header is sound, so only that block is lost."""
        decoder = Decoder(on_error="skip")
        buffer = cat021_block + _block(99, b"\x00\x00") + cat021_block
        messages = decoder.decode(buffer)
        assert len(messages) == 2, "the blocks either side of the bad one must survive"
        assert decoder.errors == 1


class TestSkipMalformedRecord:
    def test_skip_mode_resumes_after_a_truncated_record(self, cat021_block, cat021_spec):
        """A record claiming more octets than its block holds loses only its block."""
        from tests.asterix_builder import frn_map

        # An FSPEC selecting I021/130 (8 octets) with only one octet of body.
        frn = frn_map(cat021_spec)["I021/130"]
        fspec = bytearray((frn + 6) // 7)
        fspec[(frn - 1) // 7] |= 0x80 >> ((frn - 1) % 7)
        for i in range(len(fspec) - 1):
            fspec[i] |= 0x01
        bad = _block(21, bytes(fspec) + b"\x00")

        decoder = Decoder(on_error="skip")
        messages = decoder.decode(cat021_block + bad + cat021_block)
        assert len(messages) == 2
        assert decoder.errors == 1

    def test_raise_mode_propagates(self, cat021_block):
        decoder = Decoder()
        with pytest.raises(TruncatedMessageError):
            decoder.decode(cat021_block[:-2])


class TestSkipUnframeableBuffer:
    def test_a_bad_header_abandons_the_rest(self, cat021_block):
        """Without a trustworthy length there is no way to find the next block."""
        decoder = Decoder(on_error="skip")
        # Declares a length running past the end of the buffer.
        unframeable = bytes([21]) + (9999).to_bytes(2, "big") + b"\x00\x00"
        messages = decoder.decode(cat021_block + unframeable + cat021_block)
        assert len(messages) == 1, "only the blocks before the bad header survive"


class TestStreamRecovery:
    def test_truncated_tail_raises_by_default(self, cat021_block):
        decoder = Decoder()
        stream = io.BytesIO(cat021_block + cat021_block[:-3])
        with pytest.raises(TruncatedMessageError):
            decoder.decode_stream(stream)

    def test_truncated_tail_keeps_what_was_decoded_under_skip(self, cat021_block):
        """A capture cut mid-block should still yield the records before the cut."""
        decoder = Decoder(on_error="skip")
        stream = io.BytesIO(cat021_block + cat021_block + cat021_block[:-3])
        messages = decoder.decode_stream(stream)
        assert len(messages) == 2


class TestErrorCounter:
    def test_starts_at_zero(self):
        assert Decoder().errors == 0

    def test_stays_zero_in_raise_mode(self, cat021_block):
        decoder = Decoder()
        decoder.decode(cat021_block)
        assert decoder.errors == 0

    def test_counts_each_skipped_block(self, cat021_block):
        decoder = Decoder(on_error="skip")
        decoder.decode(_block(99, b"\x00") + cat021_block + _block(98, b"\x00"))
        assert decoder.errors == 2
