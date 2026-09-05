import pytest

from pyasteryx.exporters import to_arrow, to_geojson, to_pandas, to_parquet, to_records
from pyasteryx.spark import decode_partition, decode_records


def test_to_records(decoder, cat021_block):
    rows = to_records(decoder.decode(cat021_block))
    assert rows[0]["I021/010.SAC"] == 25
    assert rows[0]["I021/130.Lat"] == pytest.approx(45.0, abs=1e-4)


def test_to_pandas(decoder, cat021_block):
    df = to_pandas(decoder.decode(cat021_block + cat021_block))
    assert len(df) == 2
    assert df["I021/010.SIC"].iloc[0] == 200


def test_to_arrow(decoder, cat021_block):
    table = to_arrow(decoder.decode(cat021_block))
    assert table.num_rows == 1
    assert "I021/080.TAddr" in table.column_names


def test_to_parquet_roundtrip(tmp_path, decoder, cat021_block):
    import pyarrow.parquet as pq

    path = tmp_path / "out.parquet"
    to_parquet(decoder.decode(cat021_block), str(path))
    table = pq.read_table(str(path))
    assert table.num_rows == 1


def test_to_geojson(decoder, cat021_block):
    fc = to_geojson(decoder.decode(cat021_block))
    assert fc["type"] == "FeatureCollection"
    lon, lat = fc["features"][0]["geometry"]["coordinates"]
    assert lat == pytest.approx(45.0, abs=1e-4)
    assert lon == pytest.approx(45.0, abs=1e-4)


def test_spark_decode_records(decoder, cat021_block):
    # Pure-Python Spark helper: no pyspark needed.
    rows = decode_records(cat021_block, decoder)
    assert rows[0]["I021/010.SAC"] == 25


def test_spark_decode_records_bad_input_is_empty(decoder):
    assert decode_records(b"", decoder) == []
    assert decode_records(bytes.fromhex("630004"), decoder) == []


def test_spark_decode_partition(cat021_block):
    class Row:
        def __init__(self, payload):
            self._d = {"payload": payload}

        def __getitem__(self, k):
            return self._d[k]

    rows = [Row(cat021_block), Row(cat021_block)]
    out = list(decode_partition(rows, "payload"))
    assert len(out) == 2
    assert out[0]["I021/010.SAC"] == 25


class TestTrackExports:
    """Tracks flow through the exporters just like messages do."""

    def test_to_records_accepts_tracks(self, decoder, cat062_block):
        from pyasteryx import tracks

        rows = to_records(tracks(decoder.decode(cat062_block)))
        assert len(rows) == 1
        assert rows[0]["callsign"] == "DLH4AB"
        assert rows[0]["flight_level"] == 350.0

    def test_to_pandas_gives_named_columns(self, decoder, cat062_block):
        from pyasteryx import tracks

        df = to_pandas(tracks(decoder.decode(cat062_block * 2)))
        assert len(df) == 2
        assert df["track_number"].tolist() == [1234, 1234]
        assert "ground_speed_kt" in df.columns

    def test_geojson_detects_track_position_columns(self, decoder, cat062_block):
        from pyasteryx import tracks

        fc = to_geojson(tracks(decoder.decode(cat062_block)))
        assert len(fc["features"]) == 1
        assert fc["features"][0]["geometry"]["coordinates"] == [11.25, 45.0]

    def test_geojson_detects_cat062_item_keys_on_raw_messages(self, decoder, cat062_block):
        fc = to_geojson(decoder.decode(cat062_block))
        assert fc["features"][0]["geometry"]["coordinates"] == [11.25, 45.0]

    def test_geojson_skips_records_without_a_position(self, decoder, cat062_spec):
        from tests.asterix_builder import build_block

        sparse = build_block(cat062_spec, {"I062/010": bytes.fromhex("19C8")})
        assert to_geojson(decoder.decode(sparse))["features"] == []

    def test_geojson_does_not_latch_onto_a_sparse_first_record(
        self, decoder, cat062_spec, cat062_block
    ):
        """A positionless first record must not stop later positions exporting."""
        from tests.asterix_builder import build_block

        sparse = build_block(cat062_spec, {"I062/010": bytes.fromhex("19C8")})
        fc = to_geojson(decoder.decode(sparse + cat062_block))
        assert len(fc["features"]) == 1
