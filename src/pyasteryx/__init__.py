"""pyasteryx — a fast, specification-driven decoder for EUROCONTROL ASTERIX data.

Quick start::

    from pyasteryx import Decoder, tracks

    decoder = Decoder()

    # A recorded capture...
    for track in tracks(decoder.iter_pcap("capture.pcap")):
        print(track.track_number, track.callsign, track.flight_level)

    # ...or a live multicast feed.
    for track in tracks(decoder.iter_multicast("239.1.1.1", 8600)):
        print(track)

The public surface is deliberately small and stable: :class:`Decoder` for
reading, :class:`Message` for a raw record, :class:`Track` for a CAT062 record in
engineering units, the typed exceptions, and the specification registry for
registering extra or custom categories.
"""

from __future__ import annotations

from pyasteryx.decoder import Decoder
from pyasteryx.enums import describe
from pyasteryx.exceptions import (
    AsteryxError,
    DecodeError,
    InvalidFspecError,
    InvalidLengthError,
    SpecificationError,
    TruncatedMessageError,
    UnsupportedCategoryError,
    UnsupportedItemError,
)
from pyasteryx.models import Message
from pyasteryx.spec import CategorySpec, SpecRegistry
from pyasteryx.timing import DayResolver, to_datetime
from pyasteryx.track import Track, group_by_track, tracks

__version__ = "0.3.0"

__all__ = [
    # Reading
    "Decoder",
    # Models
    "Message",
    "Track",
    "tracks",
    "group_by_track",
    # Time
    "DayResolver",
    "to_datetime",
    # Semantics
    "describe",
    # Specifications
    "SpecRegistry",
    "CategorySpec",
    # Errors
    "AsteryxError",
    "DecodeError",
    "TruncatedMessageError",
    "InvalidLengthError",
    "InvalidFspecError",
    "UnsupportedCategoryError",
    "UnsupportedItemError",
    "SpecificationError",
    "__version__",
]
