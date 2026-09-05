"""Data models returned by the decoder.

The models are intentionally lightweight: frozen, ``slots``-based dataclasses so
that bulk decoding stays cheap on both memory and allocation time. A decoded
ASTERIX record is represented as a :class:`Message`, whose ``items`` maps each
present data-item id (e.g. ``"I021/010"``) to its decoded value.

The decoded value of a data item is a plain ``dict`` of field name -> value for
fixed/extended items, or a ``list[dict]`` for repetitive items. Keeping the leaf
values as builtins (int/float/str) keeps the ``to_*`` exporters trivial and
avoids per-field object allocation on the hot path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

# A decoded data item is a mapping of field-name -> value, or a list of those
# (repetitive items). Values are builtins: int, float, str, bool.
ItemValue = Dict[str, Any]


@dataclass(frozen=True, slots=True)
class Message:
    """A single decoded ASTERIX record.

    Attributes:
        category: The ASTERIX category number (e.g. ``21`` for CAT021).
        items: Mapping of data-item id -> decoded value, in the order the items
            appeared in the record.
    """

    category: int
    items: Dict[str, Any] = field(default_factory=dict)

    def __getitem__(self, item_id: str) -> Any:
        return self.items[item_id]

    def __contains__(self, item_id: str) -> bool:
        return item_id in self.items

    def get(self, item_id: str, default: Any = None) -> Any:
        """Return the decoded value for ``item_id`` or ``default`` if absent."""
        return self.items.get(item_id, default)

    def to_dict(self) -> Dict[str, Any]:
        """Return a flat, JSON-serialisable dict representation of the record.

        Keys are dotted paths: ``"I021/010.SAC"`` for a field, and for compound
        items the nesting continues (``"I062/110.SUM.M5"``). Repetitive items keep
        their list value under the bare item id.
        """
        out: Dict[str, Any] = {"category": self.category}
        for item_id, value in self.items.items():
            _flatten(item_id, value, out)
        return out


def _flatten(prefix: str, value: Any, out: Dict[str, Any]) -> None:
    """Recursively flatten nested dicts into dotted keys; leave lists intact."""
    if isinstance(value, dict):
        for key, sub in value.items():
            _flatten(f"{prefix}.{key}", sub, out)
    else:
        out[prefix] = value
