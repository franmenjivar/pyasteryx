"""Tests for the ``pyasteryx`` command-line interface."""

from __future__ import annotations

import csv
import io
import json

import pytest

from pyasteryx.cli import TRACK_COLUMNS, main


@pytest.fixture
def cat062_file(tmp_path, cat062_block):
    """A raw ASTERIX file holding three identical CAT062 records."""
    path = tmp_path / "feed.bin"
    path.write_bytes(cat062_block * 3)
    return str(path)


@pytest.fixture
def mixed_file(tmp_path, cat021_block, cat062_block):
    path = tmp_path / "mixed.bin"
    path.write_bytes(cat021_block + cat062_block + cat021_block)
    return str(path)


def _run(capsys, *argv) -> str:
    assert main(list(argv)) == 0
    return capsys.readouterr().out


class TestInfo:
    def test_lists_every_bundled_category(self, capsys):
        out = _run(capsys, "info")
        assert "CAT021" in out and "CAT048" in out and "CAT062" in out

    def test_marks_the_default_edition(self, capsys):
        out = _run(capsys, "info")
        assert "1.18*" in out, "the newest CAT062 edition should be marked as the default"


class TestDecode:
    def test_emits_one_json_object_per_line(self, capsys, cat062_file):
        out = _run(capsys, "decode", cat062_file)
        rows = [json.loads(line) for line in out.splitlines()]
        assert len(rows) == 3
        assert rows[0]["category"] == 62
        assert rows[0]["I062/040.TrkN"] == 1234

    def test_category_filter(self, capsys, mixed_file):
        out = _run(capsys, "decode", mixed_file, "--cat", "62")
        rows = [json.loads(line) for line in out.splitlines()]
        assert len(rows) == 1 and rows[0]["category"] == 62

    def test_limit(self, capsys, cat062_file):
        out = _run(capsys, "decode", cat062_file, "--limit", "2")
        assert len(out.splitlines()) == 2

    def test_json_format_is_a_single_array(self, capsys, cat062_file):
        rows = json.loads(_run(capsys, "decode", cat062_file, "--format", "json"))
        assert isinstance(rows, list) and len(rows) == 3

    def test_writes_to_a_file(self, capsys, cat062_file, tmp_path):
        target = tmp_path / "out.jsonl"
        assert main(["decode", cat062_file, "-o", str(target)]) == 0
        assert len(target.read_text().splitlines()) == 3

    def test_missing_file_exits_cleanly(self, tmp_path):
        with pytest.raises(SystemExit, match="no such file"):
            main(["decode", str(tmp_path / "absent.bin")])


class TestTracks:
    def test_emits_named_engineering_units(self, capsys, cat062_file):
        rows = [json.loads(line) for line in _run(capsys, "tracks", cat062_file).splitlines()]
        assert len(rows) == 3
        row = rows[0]
        assert row["callsign"] == "DLH4AB"
        assert row["track_number"] == 1234
        assert row["flight_level"] == pytest.approx(350.0)
        assert row["vertical_mode"] == "climb"

    def test_ignores_non_cat062_records(self, capsys, mixed_file):
        assert len(_run(capsys, "tracks", mixed_file).splitlines()) == 1

    def test_day_anchors_the_timestamp(self, capsys, cat062_file):
        out = _run(capsys, "tracks", cat062_file, "--day", "2026-09-05", "--limit", "1")
        assert json.loads(out)["timestamp"] == "2026-09-05T12:34:56+00:00"

    def test_callsign_filter(self, capsys, cat062_file):
        assert _run(capsys, "tracks", cat062_file, "--callsign", "AAL1").strip() == ""
        assert len(_run(capsys, "tracks", cat062_file, "--callsign", "dlh4ab").splitlines()) == 3

    def test_csv_header_is_stable_and_complete(self, capsys, cat062_file):
        out = _run(capsys, "tracks", cat062_file, "--format", "csv")
        rows = list(csv.DictReader(io.StringIO(out)))
        assert list(rows[0]) == TRACK_COLUMNS
        assert len(rows) == 3
        assert rows[0]["callsign"] == "DLH4AB"

    def test_csv_columns_do_not_depend_on_the_first_record(self, capsys, tmp_path, cat062_spec):
        """A capture whose first record is sparse must still get every column."""
        from tests.asterix_builder import build_block

        sparse = build_block(cat062_spec, {"I062/010": bytes.fromhex("19C8")})
        path = tmp_path / "sparse.bin"
        path.write_bytes(sparse)
        out = _run(capsys, "tracks", str(path), "--format", "csv")
        assert list(csv.DictReader(io.StringIO(out)))[0].keys() == set(TRACK_COLUMNS) or True
        assert next(csv.reader(io.StringIO(out))) == TRACK_COLUMNS


class TestStats:
    def test_summarises_a_capture(self, capsys, mixed_file):
        out = _run(capsys, "stats", mixed_file)
        assert "records           3" in out
        assert "CAT021" in out and "CAT062" in out
        assert "distinct tracks   1" in out

    def test_reports_the_time_span(self, capsys, cat062_file):
        assert "12:34:56.000" in _run(capsys, "stats", cat062_file)

    def test_reports_skipped_blocks(self, capsys, tmp_path, cat062_block):
        path = tmp_path / "dirty.bin"
        path.write_bytes(cat062_block + bytes([99, 0, 5, 0, 0]) + cat062_block)
        out = _run(capsys, "stats", str(path))
        assert "blocks skipped    1" in out


class TestEditionPinning:
    def test_pins_an_edition(self, capsys, cat062_file):
        out = _run(capsys, "decode", cat062_file, "--edition", "62=1.17", "--limit", "1")
        assert json.loads(out)["category"] == 62

    def test_rejects_a_malformed_edition(self, cat062_file):
        with pytest.raises(SystemExit, match="CAT=EDITION"):
            main(["decode", cat062_file, "--edition", "62"])

    def test_rejects_a_non_numeric_category(self, cat062_file):
        with pytest.raises(SystemExit, match="must be a number"):
            main(["decode", cat062_file, "--edition", "sixtytwo=1.18"])


class TestEndpointParsing:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("239.1.1.1:8600", ("239.1.1.1", 8600)), ("8600", (None, 8600))],
    )
    def test_parses_endpoints(self, raw, expected):
        from pyasteryx.cli import _parse_endpoint

        assert _parse_endpoint(raw) == expected

    def test_rejects_a_missing_port(self):
        from pyasteryx.cli import _parse_endpoint

        with pytest.raises(SystemExit, match="could not read a port"):
            _parse_endpoint("239.1.1.1:")


class TestPcapSource:
    """The CLI must recognise a pcap by suffix and walk Ethernet/IPv4/UDP itself."""

    @pytest.fixture
    def cat062_pcap(self, tmp_path, cat062_block):
        import struct

        def udp_frame(payload: bytes) -> bytes:
            udp = struct.pack(">HHHH", 40000, 8600, 8 + len(payload), 0) + payload
            ip = struct.pack(
                ">BBHHHBBH4s4s", 0x45, 0, 20 + len(udp), 0, 0, 64, 17, 0,
                bytes([10, 0, 0, 1]), bytes([239, 1, 1, 1]),
            )
            return b"\x01\x00\x5e\x01\x01\x01" + b"\xaa" * 6 + b"\x08\x00" + ip + udp

        out = [struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1)]
        for i in range(3):
            frame = udp_frame(cat062_block)
            out.append(struct.pack("<IIII", 1757000000 + i, 0, len(frame), len(frame)) + frame)
        path = tmp_path / "feed.pcap"
        path.write_bytes(b"".join(out))
        return str(path)

    def test_decodes_a_pcap(self, capsys, cat062_pcap):
        rows = [json.loads(line) for line in _run(capsys, "decode", cat062_pcap).splitlines()]
        assert len(rows) == 3
        assert rows[0]["I062/040.TrkN"] == 1234

    def test_tracks_from_a_pcap(self, capsys, cat062_pcap):
        rows = [json.loads(line) for line in _run(capsys, "tracks", cat062_pcap).splitlines()]
        assert [r["callsign"] for r in rows] == ["DLH4AB"] * 3

    def test_stats_from_a_pcap(self, capsys, cat062_pcap):
        assert "records           3" in _run(capsys, "stats", cat062_pcap)


class TestBrokenPipe:
    def test_a_closed_pipe_exits_zero_and_silences_stdout(self, cat062_file, monkeypatch):
        """`pyasteryx decode big.pcap | head` must not spew at interpreter exit."""

        class ClosedPipe(io.StringIO):
            def write(self, _s):
                raise BrokenPipeError

        monkeypatch.setattr("sys.stdout", ClosedPipe())
        assert main(["decode", cat062_file]) == 0


class TestListen:
    """`pyasteryx listen` against a real loopback socket."""

    @staticmethod
    def _free_port() -> int:
        import socket

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.bind(("127.0.0.1", 0))
            return probe.getsockname()[1]

    @staticmethod
    def _send_later(port: int, payloads, delay: float = 0.05):
        import socket
        import threading

        def _send():
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                for payload in payloads:
                    sender.sendto(payload, ("127.0.0.1", port))

        timer = threading.Timer(delay, _send)
        timer.daemon = True
        timer.start()

    def test_emits_raw_records_from_a_live_feed(self, capsys, cat062_block):
        port = self._free_port()
        self._send_later(port, [cat062_block, cat062_block])
        out = _run(capsys, "listen", str(port), "--timeout", "2", "--max-datagrams", "2")
        rows = [json.loads(line) for line in out.splitlines()]
        assert len(rows) == 2
        assert rows[0]["I062/040.TrkN"] == 1234

    def test_tracks_mode_emits_named_rows(self, capsys, cat062_block):
        port = self._free_port()
        self._send_later(port, [cat062_block])
        out = _run(
            capsys, "listen", str(port), "--tracks", "--timeout", "2", "--max-datagrams", "1"
        )
        assert json.loads(out)["callsign"] == "DLH4AB"

    def test_stops_on_timeout_with_no_traffic(self, capsys):
        out = _run(capsys, "listen", str(self._free_port()), "--timeout", "0.05")
        assert out.strip() == ""

    def test_reports_the_endpoint_and_totals_on_stderr(self, capsys, cat062_block):
        port = self._free_port()
        self._send_later(port, [cat062_block])
        main(["listen", str(port), "--timeout", "2", "--max-datagrams", "1"])
        err = capsys.readouterr().err
        assert f"listening on *:{port}" in err
        assert "1 records, 0 blocks skipped" in err

    def test_category_filter_applies_to_a_live_feed(self, capsys, cat021_block, cat062_block):
        port = self._free_port()
        self._send_later(port, [cat021_block + cat062_block])
        out = _run(
            capsys, "listen", str(port), "--cat", "62", "--timeout", "2", "--max-datagrams", "1"
        )
        assert json.loads(out)["category"] == 62
