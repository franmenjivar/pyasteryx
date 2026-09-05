"""Typed exceptions for the pyasteryx ASTERIX decoder.

All errors raised by the library derive from :class:`AsteryxError`, so callers can
catch everything with a single ``except AsteryxError`` while still being able to
distinguish specific failure modes when they need to.
"""

from __future__ import annotations


class AsteryxError(Exception):
    """Base class for every error raised by pyasteryx."""


class DecodeError(AsteryxError):
    """Base class for errors that occur while decoding a message."""


class TruncatedMessageError(DecodeError):
    """Raised when the buffer ends before a message could be fully decoded."""


class InvalidLengthError(DecodeError):
    """Raised when a data block declares a length that is impossible or inconsistent."""


class InvalidFspecError(DecodeError):
    """Raised when a Field Specification (FSPEC) is malformed or never terminates."""


class UnsupportedCategoryError(DecodeError):
    """Raised when a data block uses an ASTERIX category that has no loaded specification."""

    def __init__(self, category: int) -> None:
        self.category = category
        super().__init__(f"No specification loaded for ASTERIX category {category:03d}")


class UnsupportedItemError(DecodeError):
    """Raised when a record references a data item that the specification does not define.

    The item's length is unknown, so decoding cannot safely continue past it.
    """

    def __init__(self, category: int, frn: int, item_id: str | None = None) -> None:
        self.category = category
        self.frn = frn
        self.item_id = item_id
        target = item_id or f"FRN {frn}"
        super().__init__(
            f"CAT{category:03d}: data item {target} is present in the FSPEC "
            f"but not defined in the specification"
        )


class SpecificationError(AsteryxError):
    """Raised when a category specification file is malformed or internally inconsistent."""
