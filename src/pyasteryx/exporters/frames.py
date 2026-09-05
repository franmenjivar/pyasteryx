"""Concrete exporters for decoded ASTERIX messages and tracks.

Every exporter takes an iterable of anything with a ``to_dict()`` — a
:class:`~pyasteryx.models.Message` (raw, item-keyed columns) or a
:class:`~pyasteryx.track.Track` (flat, named, engineering-unit columns). Passing
tracks is usually what you want for analysis::

    from pyasteryx import Decoder, tracks
    from pyasteryx.exporters import to_pandas

    df = to_pandas(tracks(Decoder().iter_pcap("feed.pcap"), day=date(2026, 9, 5)))
    df.groupby("callsign")["flight_level"].max()
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Protocol



class HasToDict(Protocol):
    """Anything that can flatten itself into a row: a Message or a Track."""

    def to_dict(self) -> Dict[str, Any]: ...


#: Flattened position keys tried by :func:`to_geojson`, in order, when the
#: caller does not name them: the Track view first, then each category's
#: WGS-84 position item.
_POSITION_KEYS = (
    ("latitude", "longitude"),
    ("I062/105.Lat", "I062/105.Lon"),
    ("I021/130.Lat", "I021/130.Lon"),
    ("I021/131.Lat", "I021/131.Lon"),
)


def _missing(dep: str, extra: str = "export") -> "ModuleNotFoundError":
    return ModuleNotFoundError(
        f"{dep} is required for this exporter. Install it with: pip install 'pyasteryx[{extra}]'"
    )


def to_records(messages: Iterable[HasToDict]) -> List[Dict[str, Any]]:
    """Return a list of flat dict rows (via each item's ``to_dict()``)."""
    return [m.to_dict() for m in messages]


def to_pandas(messages: Iterable[HasToDict]):
    """Return a :class:`pandas.DataFrame` with one row per record."""
    try:
        import pandas as pd
    except ModuleNotFoundError as exc:  # pragma: no cover - environment dependent
        raise _missing("pandas") from exc
    return pd.DataFrame(to_records(messages))


def to_arrow(messages: Iterable[HasToDict]):
    """Return a :class:`pyarrow.Table` built from the records."""
    try:
        import pyarrow as pa
    except ModuleNotFoundError as exc:  # pragma: no cover - environment dependent
        raise _missing("pyarrow") from exc
    return pa.Table.from_pylist(to_records(messages))


def to_polars(messages: Iterable[HasToDict]):
    """Return a :class:`polars.DataFrame` with one row per record."""
    try:
        import polars as pl
    except ModuleNotFoundError as exc:  # pragma: no cover - environment dependent
        raise _missing("polars") from exc
    return pl.DataFrame(to_records(messages))


def to_parquet(messages: Iterable[HasToDict], path: str) -> None:
    """Write the records to a Parquet file at ``path`` (via pyarrow)."""
    try:
        import pyarrow.parquet as pq
    except ModuleNotFoundError as exc:  # pragma: no cover - environment dependent
        raise _missing("pyarrow") from exc
    pq.write_table(to_arrow(messages), path)


def to_geojson(
    messages: Iterable[HasToDict],
    lat_key: Optional[str] = None,
    lon_key: Optional[str] = None,
    properties: bool = True,
) -> Dict[str, Any]:
    """Return a GeoJSON ``FeatureCollection`` of point features.

    Records without both coordinates are skipped, which is the normal case for a
    CAT062 feed: most updates carry no fresh position.

    Args:
        messages: Decoded records or tracks.
        lat_key: Flattened key holding latitude in degrees. Detected from the
            first row when omitted, trying the :class:`~pyasteryx.track.Track`
            column names first, then CAT062's and CAT021's position items.
        lon_key: Flattened key holding longitude in degrees; detected alongside
            ``lat_key``.
        properties: If True, attach the full flat row as feature properties.

    Returns:
        A GeoJSON ``FeatureCollection`` dict, ready for :func:`json.dump`.
    """
    features: List[Dict[str, Any]] = []
    keys = (lat_key, lon_key) if lat_key and lon_key else None

    for msg in messages:
        row = msg.to_dict()
        if keys is None:
            keys = _detect_position_keys(row)
            if keys is None:
                continue
        lat = row.get(keys[0])
        lon = row.get(keys[1])
        if lat is None or lon is None:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": row if properties else {},
            }
        )
    return {"type": "FeatureCollection", "features": features}


def _detect_position_keys(row: Dict[str, Any]) -> Optional[tuple]:
    """Pick the position keys a row carries, or ``None`` if it has none.

    Returns ``None`` rather than latching onto a key pair the row only has as
    ``None``, so a sparse first record does not fix the wrong columns for the
    whole export.
    """
    for lat_key, lon_key in _POSITION_KEYS:
        if row.get(lat_key) is not None and row.get(lon_key) is not None:
            return lat_key, lon_key
    return None
