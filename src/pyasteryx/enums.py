"""Human-readable meanings for ASTERIX coded fields.

The wire format encodes most status and classification fields as small integers:
``I062/080.SRC == 3`` is meaningful only if you have the CAT062 specification
open next to you. This module holds the code -> meaning tables so that
:class:`~pyasteryx.track.Track` (and anyone who wants them) can present
``"triangulation"`` instead of ``3``.

The tables are deliberately plain dicts rather than :class:`enum.Enum` classes:
lookups stay a dict access on the hot path, unknown codes degrade to ``None``
instead of raising, and adding a code as editions evolve is a data change.

Use :func:`describe` for a single lookup, or index the tables directly::

    from pyasteryx.enums import CAT062

    CAT062["I062/080"]["SRC"][3]        # 'triangulation'
    describe(62, "I062/080", "SRC", 3)  # 'triangulation'
"""

from __future__ import annotations

from typing import Any

__all__ = ["CAT062", "CAT021", "CAT048", "TABLES", "describe"]


# --- CAT062: System Track Data ------------------------------------------------

_ALTITUDE_SOURCE = {
    0: "no source",
    1: "GNSS",
    2: "3D radar",
    3: "triangulation",
    4: "height from coverage",
    5: "speed look-up table",
    6: "default height",
    7: "multilateration",
}

_MODE_4_5 = {0: "no interrogation", 1: "friendly", 2: "unknown", 3: "no reply"}

_EMERGENCY = {
    0: "no emergency",
    1: "general emergency",
    2: "lifeguard / medical",
    3: "minimum fuel",
    4: "no communications",
    5: "unlawful interference",
    6: "downed aircraft",
}

_TRANSVERSAL = {0: "constant course", 1: "right turn", 2: "left turn", 3: "undetermined"}
_LONGITUDINAL = {0: "constant groundspeed", 1: "increasing", 2: "decreasing", 3: "undetermined"}
_VERTICAL = {0: "level", 1: "climb", 2: "descent", 3: "undetermined"}

_EMITTER_CATEGORY = {
    0: "no information",
    1: "light aircraft (<7000 kg)",
    2: "reserved",
    3: "7000-136000 kg",
    4: "heavy (>136000 kg)",
    5: "highly manoeuvrable",
    6: "reserved",
    7: "reserved",
    8: "reserved",
    9: "reserved",
    10: "rotocraft",
    11: "glider / sailplane",
    12: "lighter-than-air",
    13: "unmanned aerial vehicle",
    14: "space / transatmospheric",
    15: "ultralight / hang-glider / paraglider",
    16: "parachutist / skydiver",
    17: "reserved",
    18: "reserved",
    19: "reserved",
    20: "surface emergency vehicle",
    21: "surface service vehicle",
    22: "fixed ground or tethered obstruction",
    23: "cluster obstacle",
    24: "line obstacle",
}

_REPORT_TYPE = {
    1: "single PSR plot",
    2: "single SSR plot",
    3: "SSR + PSR plot",
    4: "single Mode S all-call",
    5: "single Mode S roll-call",
    6: "Mode S all-call + PSR",
    7: "Mode S roll-call + PSR",
    8: "ADS-B",
    9: "ADS-C",
}

_FLIGHT_STAGE = {0: "unknown", 1: "take-off", 2: "landing", 3: "reserved"}

_SURVEILLANCE_STATUS = {0: "no condition", 1: "permanent alert", 2: "temporary alert", 3: "SPI"}

CAT062: dict[str, dict[str, dict[int, str]]] = {
    "I062/060": {
        "V": {0: "code validated", 1: "code not validated"},
        "G": {0: "default", 1: "garbled code"},
        "CH": {0: "no change", 1: "Mode 3/A has changed"},
    },
    "I062/080": {
        "MON": {0: "multisensor track", 1: "monosensor track"},
        "SPI": {0: "default", 1: "SPI present"},
        "MRH": {0: "barometric altitude reliable", 1: "geometric altitude reliable"},
        "SRC": _ALTITUDE_SOURCE,
        "CNF": {0: "confirmed track", 1: "track in initialisation"},
        "SIM": {0: "actual track", 1: "simulated track"},
        "TSE": {0: "default", 1: "last report for this track"},
        "TSB": {0: "default", 1: "first report for this track"},
        "FPC": {0: "not flight-plan correlated", 1: "flight-plan correlated"},
        "AFF": {0: "default", 1: "ADS-B data inconsistent"},
        "STP": {0: "default", 1: "slave track promotion"},
        "KOS": {0: "complementary service", 1: "background service"},
        "AMA": {0: "default", 1: "track from an amalgamation process"},
        "MD4": _MODE_4_5,
        "MD5": _MODE_4_5,
        "ME": {0: "default", 1: "military emergency"},
        "MI": {0: "default", 1: "military identification"},
        "CST": {0: "default", 1: "age of one position exceeds threshold"},
        "PSR": {0: "default", 1: "age of PSR track exceeds threshold"},
        "SSR": {0: "default", 1: "age of SSR track exceeds threshold"},
        "MDS": {0: "default", 1: "age of Mode S track exceeds threshold"},
        "ADS": {0: "default", 1: "age of ADS-B track exceeds threshold"},
        "SUC": {0: "default", 1: "special used code"},
        "AAC": {0: "default", 1: "assigned Mode A code conflict"},
        "SDS": {
            0: "combined", 1: "co-operative only",
            2: "non co-operative only", 3: "not defined",
        },
        "EMS": _EMERGENCY,
        "PFT": {0: "no indication", 1: "potential false track"},
        "FPLT": {0: "default", 1: "track created / updated with a flight plan"},
        "DUPT": {0: "default", 1: "duplicate Mode 3/A code"},
        "DUPF": {0: "default", 1: "duplicate flight plan"},
        "DUPM": {0: "default", 1: "duplicate flight plan due to manual correlation"},
        "SFC": {0: "default", 1: "surface target"},
        "IDD": {0: "no doubt", 1: "duplicate Mode 5 pair NO/PIN"},
        "IEC": {0: "default", 1: "inconsistent emergency and coasting"},
    },
    "I062/200": {
        "TRANSA": _TRANSVERSAL,
        "LONGA": _LONGITUDINAL,
        "VERTA": _VERTICAL,
        "ADF": {0: "no altitude discrepancy", 1: "altitude discrepancy"},
    },
    "I062/290": {},
    "I062/340": {
        "TYP": _REPORT_TYPE,
        "SIM": {0: "actual target report", 1: "simulated target report"},
        "RAB": {0: "report from target transponder", 1: "report from field monitor"},
        "TST": {0: "real target report", 1: "test target report"},
    },
    "I062/380": {
        "EMC": _EMITTER_CATEGORY,
        "ECAT": _EMITTER_CATEGORY,
        "SAS": {0: "no source information", 1: "source information provided"},
        "SRC": {
            0: "unknown", 1: "aircraft altitude",
            2: "FCU/MCP selected altitude", 3: "FMS selected altitude",
        },
        "MV": {0: "not active", 1: "active"},
        "AH": {0: "not active", 1: "active"},
        "AM": {0: "not active", 1: "active"},
        "STAT": _SURVEILLANCE_STATUS,
        "GBS": {0: "airborne", 1: "on ground"},
    },
    "I062/390": {},
    "I062/510": {},
}


# --- CAT021: ADS-B Target Reports --------------------------------------------

CAT021: dict[str, dict[str, dict[int, str]]] = {
    "I021/008": {"ECAT": _EMITTER_CATEGORY},
    "I021/020": {"ECAT": _EMITTER_CATEGORY},
    "I021/040": {
        "ATP": {
            0: "24-bit ICAO address",
            1: "duplicate address",
            2: "surface vehicle address",
            3: "anonymous address",
        },
        "ARC": {0: "25 ft", 1: "100 ft", 2: "unknown", 3: "invalid"},
        "RC": {0: "default", 1: "range check passed"},
        "RAB": {0: "report from target transponder", 1: "report from field monitor"},
        "DCR": {0: "no differential correction", 1: "differential correction"},
        "GBS": {0: "airborne", 1: "on ground"},
        "SIM": {0: "actual report", 1: "simulated report"},
        "TST": {0: "default", 1: "test target"},
        "SAA": {0: "equipped with selected-altitude capability", 1: "not equipped"},
        "CL": {0: "report valid", 1: "report suspect", 2: "no information", 3: "reserved"},
    },
    "I021/200": {
        "ICF": {0: "no intent change", 1: "intent change"},
        "LNAV": {0: "LNAV mode engaged", 1: "LNAV mode not engaged"},
        "PS": _EMERGENCY,
        "SS": _SURVEILLANCE_STATUS,
    },
}


# --- CAT048: Monoradar Target Reports ----------------------------------------

CAT048: dict[str, dict[str, dict[int, str]]] = {
    "I048/020": {
        "TYP": {
            0: "no detection",
            1: "single PSR detection",
            2: "single SSR detection",
            3: "SSR + PSR detection",
            4: "single Mode S all-call",
            5: "single Mode S roll-call",
            6: "Mode S all-call + PSR",
            7: "Mode S roll-call + PSR",
        },
        "SIM": {0: "actual target report", 1: "simulated target report"},
        "RDP": {0: "RDP chain 1", 1: "RDP chain 2"},
        "SPI": {0: "default", 1: "special position identification"},
        "RAB": {0: "report from aircraft transponder", 1: "report from field monitor"},
        "TST": {0: "real target report", 1: "test target report"},
        "FOE": {
            0: "no Mode 4 interrogation", 1: "friendly target",
            2: "unknown target", 3: "no reply",
        },
    },
    "I048/070": {
        "V": {0: "code validated", 1: "code not validated"},
        "G": {0: "default", 1: "garbled code"},
        "L": {0: "Mode-3/A code derived from the reply", 1: "smoothed Mode-3/A code"},
    },
    "I048/090": {
        "V": {0: "code validated", 1: "code not validated"},
        "G": {0: "default", 1: "garbled code"},
    },
}


#: Every table, keyed by ASTERIX category number.
TABLES: dict[int, dict[str, dict[str, dict[int, str]]]] = {
    21: CAT021,
    48: CAT048,
    62: CAT062,
}


def describe(category: int, item_id: str, field: str, value: Any) -> str | None:
    """Return the meaning of a coded field value, or ``None`` if unknown.

    Args:
        category: ASTERIX category number (e.g. ``62``).
        item_id: Data item id (e.g. ``"I062/080"``).
        field: Field name within the item (e.g. ``"SRC"``).
        value: The decoded field value.

    Returns:
        The human-readable meaning, or ``None`` when the category, item, field or
        code has no entry. Never raises, so it is safe to call on every field of
        every record.
    """
    try:
        return TABLES[category][item_id][field][value]
    except (KeyError, TypeError):
        return None
