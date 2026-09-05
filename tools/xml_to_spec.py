#!/usr/bin/env python3
"""Convert CroatiaControlLtd/asterix XML category definitions into pyasteryx JSON specs.

The XML files (``asterix_catXXX_v_v.xml``) are an authoritative, decoder-oriented
encoding of the EUROCONTROL ASTERIX specifications. This tool translates one into
the JSON shape that :mod:`pyasteryx.spec.loader` consumes, so that adding or updating a
category/edition is a reproducible data step rather than hand transcription.

Usage::

    python tools/xml_to_spec.py path/to/asterix_cat021_2_6.xml \
        src/pyasteryx/spec/data/cat021/2.6.json

Specs are written minified. Pass --pretty for an indented file when you want to
diff one conversion against another.

The mapping is intentionally lossless for everything the decoder needs (bit
layout, length, scaling, signedness, character encodings, UAP) and drops only
human-readable enumerations (BitsValue) that carry no decoding information.
"""

from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

# Bits short-names that carry no decodable information.
_SKIP_NAMES = {"fx", "spare", "sb", "spare bits"}


def _norm_name(el: ET.Element) -> str:
    return (el.findtext("BitsShortName") or "").strip()


def _convert_bits(fixed_el: ET.Element, skip_fx: bool) -> list[dict[str, Any]]:
    """Convert the ``<Bits>`` children of a ``<Fixed>`` element into field dicts."""
    fields: list[dict[str, Any]] = []
    for bits in fixed_el.findall("Bits"):
        is_fx = bits.attrib.get("fx") == "1"
        if skip_fx and is_fx:
            continue
        # Presence bits belong to a compound primary subfield, handled elsewhere.
        if bits.find("BitsPresence") is not None:
            continue

        name = _norm_name(bits)
        if not name or name.lower() in _SKIP_NAMES or is_fx:
            continue

        if "bit" in bits.attrib:
            hi = lo = int(bits.attrib["bit"])
        else:
            a, b = int(bits.attrib["from"]), int(bits.attrib["to"])
            hi, lo = max(a, b), min(a, b)

        field: dict[str, Any] = {"name": name, "from": hi, "to": lo}

        encode = bits.attrib.get("encode")
        if encode == "signed":
            field["signed"] = True
        elif encode in ("hex", "octal", "ascii", "6bitschar"):
            field["encode"] = encode

        unit = bits.find("BitsUnit")
        if unit is not None:
            scale = unit.attrib.get("scale")
            if scale is not None and float(scale) != 1.0:
                field["scale"] = float(scale)
            if unit.text and unit.text.strip():
                field["unit"] = unit.text.strip()

        fields.append(field)
    return fields


# A Mode S BDS register: 7 octets (56 bits) of MB data plus a one-octet
# BDS1/BDS2 address, per I0xx/250 in every category that carries Mode S MB data.
def _bds_block() -> tuple[int, list[dict[str, Any]]]:
    return 8, [
        {"name": "MB", "from": 64, "to": 9, "encode": "hex"},
        {"name": "BDS1", "from": 8, "to": 5},
        {"name": "BDS2", "from": 4, "to": 1},
    ]


def _repetition_block(el: ET.Element) -> tuple[int, list[dict[str, Any]]]:
    """Return (octet length, fields) for the block a Repetitive/BDS item repeats."""
    if el.tag == "BDS":
        return _bds_block()
    if el.tag == "Fixed":
        return int(el.attrib["length"]), _convert_bits(el, skip_fx=False)
    raise ValueError(f"Unsupported repetition block <{el.tag}>")


def _convert_format_element(el: ET.Element) -> dict[str, Any]:
    """Convert one structural element (Fixed/Variable/Repetitive/Compound/Explicit/BDS)."""
    tag = el.tag

    if tag == "Fixed":
        return {
            "format": "fixed",
            "length": int(el.attrib["length"]),
            "fields": _convert_bits(el, skip_fx=False),
        }

    if tag == "BDS":
        length, fields = _bds_block()
        return {"format": "fixed", "length": length, "fields": fields}

    if tag == "Variable":
        parts = [
            {"length": int(fixed.attrib["length"]), "fields": _convert_bits(fixed, skip_fx=True)}
            for fixed in el.findall("Fixed")
        ]
        return {"format": "extended", "parts": parts}

    if tag == "Repetitive":
        block = next(iter(el))
        length, fields = _repetition_block(block)
        return {"format": "repetitive", "length": length, "fields": fields}

    if tag == "Compound":
        children = list(el)
        primary = children[0]  # a <Variable> whose bits' BitsPresence order the subfields
        presence: list[str] = []
        for fixed in primary.findall("Fixed"):
            for bits in fixed.findall("Bits"):
                if bits.find("BitsPresence") is not None:
                    presence.append(_norm_name(bits) or f"SF{len(presence) + 1}")

        subfields = []
        for index, sub_el in enumerate(children[1:]):
            sub = _convert_format_element(sub_el)
            key = presence[index] if index < len(presence) else f"SF{index + 1}"
            sub["id"] = key
            sub["name"] = key
            subfields.append(sub)
        return {"format": "compound", "subfields": subfields}

    if tag == "Explicit":
        return {"format": "explicit"}

    raise ValueError(f"Unsupported format element <{tag}>")


def _convert_item(cat: int, di: ET.Element) -> dict[str, Any]:
    raw_id = di.attrib["id"]
    fmt_el = di.find("DataItemFormat")
    if fmt_el is None:
        return {}
    inner = next(iter(fmt_el))
    spec = _convert_format_element(inner)
    spec["id"] = f"I{cat:03d}/{raw_id}"
    spec["name"] = (di.findtext("DataItemName") or raw_id).strip()
    return spec


def _convert_uap(cat: int, uap_el: ET.Element, known_ids: set) -> list[str | None]:
    uap: list[str | None] = []
    for u in uap_el.findall("UAPItem"):
        frn = u.attrib.get("frn", "")
        if not frn.isdigit():
            continue  # FX markers and the like are not FRNs.
        frn_i = int(frn)
        while len(uap) < frn_i:
            uap.append(None)
        text = (u.text or "").strip()
        if text in ("", "-"):
            uap[frn_i - 1] = None
        else:
            item_id = f"I{cat:03d}/{text}"
            uap[frn_i - 1] = item_id if item_id in known_ids else None
    return uap


def convert(xml_path: Path) -> dict[str, Any]:
    root = ET.parse(xml_path).getroot()
    cat = int(root.attrib["id"])
    edition = root.attrib.get("ver", "")
    name = root.attrib.get("name", f"CAT{cat:03d}")

    items = []
    known_ids = set()
    for di in root.findall("DataItem"):
        spec = _convert_item(cat, di)
        if spec:
            items.append(spec)
            known_ids.add(spec["id"])

    uap_el = root.find("UAP")
    uap = _convert_uap(cat, uap_el, known_ids) if uap_el is not None else []

    return {
        "category": cat,
        "edition": edition,
        "name": name,
        "source": f"CroatiaControlLtd/asterix {xml_path.name}",
        "uap": uap,
        "items": items,
    }


def main(argv: list[str]) -> int:
    argv = list(argv)
    # Bundled specs ship minified: indentation is well over half the file size
    # and nothing reads these by eye. Pass --pretty when diffing a conversion.
    pretty = "--pretty" in argv
    if pretty:
        argv.remove("--pretty")
    if len(argv) != 3:
        print(__doc__)
        return 2
    xml_path = Path(argv[1])
    out_path = Path(argv[2])
    spec = convert(xml_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if pretty:
        text = json.dumps(spec, indent=2, ensure_ascii=False) + "\n"
    else:
        text = json.dumps(spec, separators=(",", ":"), ensure_ascii=False)
    out_path.write_text(text, encoding="utf-8")
    n_items = len(spec["items"])
    n_frn = sum(1 for x in spec["uap"] if x)
    print(
        f"CAT{spec['category']:03d} v{spec['edition']}: "
        f"{n_items} items, {n_frn} UAP slots -> {out_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
