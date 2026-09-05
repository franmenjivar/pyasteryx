"""Loading of category specifications from JSON data files.

The on-disk format is JSON (chosen for zero-dependency parsing) and the bundled
files are minified — indentation was over half their size and nothing reads them
by eye. A category file looks like::

    {
      "category": 21,
      "name": "...",
      "edition": "2.4",
      "uap": ["I021/010", "I021/040", null, ...],
      "items": [
        {"id": "I021/010", "name": "...", "format": "fixed", "length": 2,
         "fields": [{"name": "SAC", "from": 16, "to": 9},
                    {"name": "SIC", "from": 8,  "to": 1}]},
        ...
      ]
    }

Files live at ``spec/data/cat<NNN>/<edition>.json``, so a category and edition
can be discovered from the path alone. :func:`iter_bundled_paths` relies on that
to let :class:`~pyasteryx.spec.SpecRegistry` index what is available without
parsing anything.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from pyasteryx.exceptions import SpecificationError
from pyasteryx.spec.model import (
    COMPOUND,
    EXPLICIT,
    EXTENDED,
    FIXED,
    REPETITIVE,
    CategorySpec,
    ExtentSpec,
    FieldSpec,
    ItemSpec,
)

_DATA_DIR = Path(__file__).parent / "data"

_VALID_FORMATS = {FIXED, EXTENDED, REPETITIVE, COMPOUND, EXPLICIT}

# "cat062" -> 62
_CATEGORY_DIR = re.compile(r"^cat(\d+)$")


def _field_from_json(raw: dict[str, Any]) -> FieldSpec:
    try:
        return FieldSpec(
            name=raw["name"],
            bit_from=int(raw["from"]),
            bit_to=int(raw.get("to", raw["from"])),
            signed=bool(raw.get("signed", False)),
            scale=raw.get("scale"),
            encode=raw.get("encode"),
            unit=raw.get("unit"),
        )
    except KeyError as exc:
        raise SpecificationError(f"Field is missing required key {exc}") from exc


def _fields_from_json(raws: list[dict[str, Any]]) -> tuple[FieldSpec, ...]:
    return tuple(_field_from_json(f) for f in raws)


def _item_from_json(raw: dict[str, Any]) -> ItemSpec:
    try:
        item_id = raw["id"]
        fmt = raw["format"]
    except KeyError as exc:
        raise SpecificationError(f"Data item is missing required key {exc}") from exc

    if fmt not in _VALID_FORMATS:
        raise SpecificationError(f"Item {item_id}: unknown format {fmt!r}")

    name = raw.get("name", item_id)

    if fmt == FIXED:
        return ItemSpec(
            item_id=item_id,
            name=name,
            fmt=FIXED,
            length=int(raw["length"]),
            fields=_fields_from_json(raw.get("fields", [])),
        )

    if fmt == EXTENDED:
        parts = tuple(
            ExtentSpec(length=int(part["length"]), fields=_fields_from_json(part.get("fields", [])))
            for part in raw.get("parts", [])
        )
        if not parts:
            raise SpecificationError(f"Item {item_id}: extended item needs at least one part")
        return ItemSpec(item_id=item_id, name=name, fmt=EXTENDED, parts=parts)

    if fmt == REPETITIVE:
        return ItemSpec(
            item_id=item_id,
            name=name,
            fmt=REPETITIVE,
            length=int(raw["length"]),
            fields=_fields_from_json(raw.get("fields", [])),
        )

    if fmt == EXPLICIT:
        return ItemSpec(item_id=item_id, name=name, fmt=EXPLICIT)

    # COMPOUND
    subfields = tuple(_item_from_json(sub) for sub in raw.get("subfields", []))
    if not subfields:
        raise SpecificationError(f"Item {item_id}: compound item needs subfields")
    return ItemSpec(item_id=item_id, name=name, fmt=COMPOUND, subfields=subfields)


def category_from_dict(raw: dict[str, Any]) -> CategorySpec:
    """Build a :class:`CategorySpec` from an already-parsed JSON mapping."""
    try:
        category = int(raw["category"])
        uap_raw: list[str | None] = raw["uap"]
        items_raw: list[dict[str, Any]] = raw["items"]
    except KeyError as exc:
        raise SpecificationError(f"Category spec is missing required key {exc}") from exc

    items = {}
    for item_raw in items_raw:
        item = _item_from_json(item_raw)
        items[item.item_id] = item

    # Validate the UAP references items that exist (spares/None are allowed).
    for frn, item_id in enumerate(uap_raw, start=1):
        if item_id is not None and item_id not in items:
            raise SpecificationError(
                f"CAT{category:03d}: UAP FRN {frn} references undefined item {item_id!r}"
            )

    return CategorySpec(
        category=category,
        name=raw.get("name", f"CAT{category:03d}"),
        edition=str(raw.get("edition", "")),
        uap=tuple(uap_raw),
        items=items,
    )


def load_category_file(path: Path) -> CategorySpec:
    """Load and parse a single category specification file."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SpecificationError(f"Could not read specification {path}: {exc}") from exc
    return category_from_dict(raw)


def iter_bundled_paths() -> Iterator[tuple[int, str, Path]]:
    """Yield ``(category, edition, path)`` for every bundled specification file.

    The category and edition come from the path (``cat062/1.18.json``), so this
    walks the data directory without opening or parsing anything. That is what
    lets the registry know which categories and editions exist while deferring
    the cost of loading them until one is actually decoded.
    """
    if not _DATA_DIR.is_dir():  # pragma: no cover - only if the wheel is broken
        return
    for category_dir in sorted(_DATA_DIR.iterdir()):
        match = _CATEGORY_DIR.match(category_dir.name)
        if not match or not category_dir.is_dir():
            continue
        category = int(match.group(1))
        for path in sorted(category_dir.glob("*.json")):
            yield category, path.stem, path


def load_bundled_categories() -> list[CategorySpec]:
    """Load and parse every bundled category specification, across all editions.

    This is the eager counterpart to :func:`iter_bundled_paths`. Prefer
    :meth:`~pyasteryx.spec.SpecRegistry.with_bundled`, which loads each category
    only when it is first decoded.
    """
    return [load_category_file(path) for _, _, path in iter_bundled_paths()]
