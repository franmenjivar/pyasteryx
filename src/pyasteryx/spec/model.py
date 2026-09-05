"""In-memory model of an ASTERIX category specification.

Specifications are loaded from data files (see :mod:`pyasteryx.spec.loader`) into these
frozen dataclasses. The parser interprets them at decode time, so adding a new
category — or a new edition of an existing one — is a data change, not a code
change.

Bit numbering follows the ASTERIX convention: within a data item, bits are
numbered from 1 (the LSB of the last octet) up to ``8 * length`` (the MSB of the
first octet). A field therefore spans an inclusive range ``[bit_to, bit_from]``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Supported data-item encodings.
FIXED = "fixed"
EXTENDED = "extended"
REPETITIVE = "repetitive"
COMPOUND = "compound"
EXPLICIT = "explicit"


@dataclass(frozen=True, slots=True)
class FieldSpec:
    """A single named field inside a data item.

    Attributes:
        name: Field name (e.g. ``"SAC"``).
        bit_from: Most-significant bit position (1-indexed, inclusive).
        bit_to: Least-significant bit position (1-indexed, inclusive).
        signed: Whether the raw value is two's-complement signed.
        scale: Optional multiplier applied to the raw value (LSB resolution).
        encode: Optional presentation hint: ``"hex"`` or ``"octal"``.
        unit: Optional unit string, for documentation/export.
    """

    name: str
    bit_from: int
    bit_to: int
    signed: bool = False
    scale: float | None = None
    encode: str | None = None
    unit: str | None = None

    @property
    def width(self) -> int:
        """Number of bits the field spans."""
        return self.bit_from - self.bit_to + 1


@dataclass(frozen=True, slots=True)
class ExtentSpec:
    """One extent (variable-length group) of an extended data item.

    Attributes:
        length: Number of octets in this extent. The FX bit is always bit 1 (the
            LSB) of the extent's last octet and is consumed automatically.
        fields: The fields carried by this extent.
    """

    length: int
    fields: tuple[FieldSpec, ...]


@dataclass(frozen=True, slots=True)
class ItemSpec:
    """Specification of a single ASTERIX data item.

    The meaningful attributes depend on ``fmt``:

    * ``fixed``: ``length`` and ``fields``.
    * ``extended``: ``parts`` — one :class:`ExtentSpec` per variable-length
      extent. If an item extends beyond its defined extents, the last extent's
      layout is reused for each further group (repeating extension).
    * ``repetitive``: ``length`` (octets per repetition) and ``fields``.
    * ``compound``: ``subfields`` — the ordered subitems selected by the
      compound item's primary subfield.
    * ``explicit``: a length-prefixed opaque block (Reserved/Special fields);
      decoded to raw hex.
    """

    item_id: str
    name: str
    fmt: str
    length: int = 0
    fields: tuple[FieldSpec, ...] = ()
    parts: tuple[ExtentSpec, ...] = ()
    subfields: tuple[ItemSpec, ...] = ()


@dataclass(frozen=True, slots=True)
class CategorySpec:
    """Specification of an ASTERIX category.

    Attributes:
        category: Category number (e.g. ``21``).
        name: Human-readable category name.
        edition: Edition string of the underlying standard.
        uap: The User Application Profile: ``uap[frn - 1]`` gives the item id for
            Field Reference Number ``frn``, or ``None`` for spare/undefined slots.
        items: Mapping of item id -> :class:`ItemSpec`.
    """

    category: int
    name: str
    edition: str
    uap: tuple[str | None, ...]
    items: dict[str, ItemSpec] = field(default_factory=dict)

    def item_for_frn(self, frn: int) -> str | None:
        """Return the item id for a Field Reference Number, or ``None``."""
        if 1 <= frn <= len(self.uap):
            return self.uap[frn - 1]
        return None
