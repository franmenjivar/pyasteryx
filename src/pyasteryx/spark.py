"""PySpark integration helpers.

This module makes pyasteryx first-class in a Spark pipeline. It is optional: nothing
here is imported by ``import pyasteryx``, and ``pyspark`` is only needed for the
``pandas_udf`` factory (install with ``pyasteryx[spark]``). The plain-Python helpers
(:func:`decode_records`, :func:`decode_partition`) have no Spark dependency and
are what you hand to ``mapPartitions``/``mapInPandas``.

Design:
* One :class:`~pyasteryx.decoder.Decoder` is built per partition/worker, never per row
  — decoders are immutable and cheap to reuse, but constructing one per row would
  dominate the runtime.
* The vectorized :func:`asterix_decode_udf` decodes an Arrow batch of ``binary``
  values at once and returns a JSON column, keeping the Python/JVM boundary
  crossings proportional to the number of *batches*, not rows.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from typing import Any

from pyasteryx.decoder import Decoder
from pyasteryx.exceptions import DecodeError

RawBytes = bytes | bytearray | memoryview


def decode_records(raw: RawBytes | None, decoder: Decoder) -> list[dict[str, Any]]:
    """Decode one raw ASTERIX buffer into a list of flat dict rows.

    Never raises: a malformed/empty buffer yields an empty list, which keeps a
    Spark job from failing on a single bad packet. Use a strict
    :class:`~pyasteryx.decoder.Decoder` and call :meth:`Decoder.decode` directly if you
    want hard failures instead.
    """
    if not raw:
        return []
    try:
        return [m.to_dict() for m in decoder.iter_messages(bytes(raw))]
    except DecodeError:
        return []


def decode_partition(
    rows: Iterable[Any],
    column: str,
    editions: dict[int, str] | None = None,
) -> Iterator[dict[str, Any]]:
    """Decode a partition of Spark ``Row``s, yielding one flat dict per record.

    Build for ``rdd.mapPartitions`` / ``df.rdd.mapPartitions``::

        flat = df.rdd.mapPartitions(
            lambda rows: decode_partition(rows, "payload", editions={62: "1.18"})
        )

    One decoder is constructed per partition and reused for every row.
    """
    decoder = Decoder(editions=editions)
    for row in rows:
        raw = row[column]
        yield from decode_records(raw, decoder)


def asterix_decode_udf(editions: dict[int, str] | None = None):
    """Return a vectorized ``pandas_udf`` mapping a ``binary`` column to JSON.

    The returned UDF takes a column whose each value is a raw ASTERIX buffer and
    returns a ``string`` column holding a JSON array of the decoded records for
    that buffer (empty array for undecodable input). Explode/parse it downstream::

        from pyspark.sql.functions import col, from_json, explode
        decode = asterix_decode_udf(editions={21: "2.6"})
        df = df.withColumn("records", decode(col("payload")))

    Requires ``pyspark`` (``pip install 'pyasteryx[spark]'``).
    """
    try:
        import pandas as pd
        from pyspark.sql.functions import pandas_udf
        from pyspark.sql.types import StringType
    except ModuleNotFoundError as exc:  # pragma: no cover - environment dependent
        raise ModuleNotFoundError(
            "pyspark and pandas are required for asterix_decode_udf. "
            "Install them with: pip install 'pyasteryx[spark]'"
        ) from exc

    decoder = Decoder(editions=editions)

    @pandas_udf(StringType())
    def _decode(batch: pd.Series) -> pd.Series:
        return pd.Series([json.dumps(decode_records(raw, decoder)) for raw in batch])

    return _decode
