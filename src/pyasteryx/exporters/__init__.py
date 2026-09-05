"""Exporters: turn decoded messages into data-engineering friendly structures.

Every exporter accepts any iterable of :class:`~pyasteryx.models.Message` and produces
flat rows via :meth:`Message.to_dict`. The heavier dependencies (pandas, pyarrow,
polars) are optional and imported lazily, so ``import pyasteryx`` stays dependency-free;
install them with the ``pyasteryx[export]`` extra.
"""

from pyasteryx.exporters.frames import (
    to_arrow,
    to_geojson,
    to_pandas,
    to_parquet,
    to_polars,
    to_records,
)

__all__ = [
    "to_records",
    "to_pandas",
    "to_arrow",
    "to_polars",
    "to_parquet",
    "to_geojson",
]
