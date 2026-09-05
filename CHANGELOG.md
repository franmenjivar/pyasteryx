# Changelog

All notable changes to this project are documented here. This project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] — 2026-09-05

First release published to PyPI, as `pyasteryx`.

### Changed — breaking

- **Renamed the package from `atx` to `pyasteryx`.** The name `atx` was already
  taken on PyPI by an unrelated project, so `pip install atx` could never have
  installed this library. Update imports: `from atx import Decoder` becomes
  `from pyasteryx import Decoder`.
- **Renamed the base exception `AtxError` to `AsteryxError`.**
- **Raised the minimum Python to 3.10.** The models use `dataclass(slots=True)`,
  which is 3.10+; the previous `requires-python = ">=3.9"` would have installed
  on 3.9 and then failed at import.

### Added

- **`Track`** — a typed view over a CAT062 system-track record, exposing
  callsign, ICAO address, Mode 3/A, position, flight level, ground speed in
  knots, track angle, vertical rate, lifecycle flags and more, in engineering
  units, resolved from whichever data item carries them.
- **`tracks()`** to wrap a message stream, and **`group_by_track()`** to
  assemble trajectories keyed by source and track number.
- **Live UDP and IP multicast feeds**: `Decoder.iter_udp()`,
  `Decoder.iter_multicast()`, and the lower-level `pyasteryx.io.net`.
- **Absolute timestamps**: `pyasteryx.timing` converts ASTERIX time-of-day to
  timezone-aware UTC datetimes, with a `DayResolver` that follows the midnight
  wrap so trajectories do not jump backwards a day at 00:00 UTC.
- **Coded-field meanings**: `pyasteryx.enums` maps status and classification
  codes to text for CAT021, CAT048 and CAT062, via `describe()`.
- **A command-line interface**, installed as `pyasteryx`: `info`, `stats`,
  `decode`, `tracks` and `listen`, with JSONL/JSON/CSV output, category and
  callsign filters, and edition pinning. Everything streams.
- **`Decoder.errors`**, counting blocks skipped under `on_error="skip"`, and
  **`Decoder.registry`**.
- Exporters now accept tracks as well as messages, and `to_geojson()` detects
  the position columns instead of assuming CAT021's.
- Packaging: `LICENSE`, `CHANGELOG.md`, keywords, trove classifiers, `mypy`
  configuration and a CI workflow.

### Performance and size

- **Specifications now load lazily.** `SpecRegistry.with_bundled()` indexes the
  bundled files by path instead of parsing all five up front, and parses one on
  first use. Constructing a `Decoder()` went from 7.9 ms and 298 KiB to 0.5 ms
  and 10 KiB; a CAT062-only decoder now holds 105 KiB rather than 298 KiB,
  because it never parses CAT021, CAT048, or the older CAT062 edition.
  `SpecRegistry(load_bundled_categories())` still loads everything eagerly.
- **Bundled specifications are shipped minified**, which was over half their
  on-disk size: 199 KB to 81 KB. `tools/xml_to_spec.py` now writes minified by
  default and takes `--pretty` for a diffable file. The wheel is 70 KB and the
  installed package 222 KB, down from 71 KB and 329 KB.
- Added `SpecRegistry.is_loaded()` and `pyasteryx.spec.iter_bundled_paths()`.

### Fixed

- **`on_error="skip"` now actually skips.** A single malformed block used to
  abandon the entire remaining buffer. A block whose header framed correctly is
  now skipped precisely, and decoding resumes at the next block; only an
  unreadable header still forces the rest of the buffer to be dropped.
- **A truncated capture no longer discards everything under `on_error="skip"`.**
  Stream framing errors were raised from outside the handler, so a file cut
  mid-block lost every record, not just the incomplete one.
- Corrected the author email in the project metadata.

### Removed

- The PyCharm `main.py` scaffold and the checked-in `.idea/` directory.

## [0.2.0] — 2026-07-15

Pre-release, never published. Specification-driven decoder for CAT021, CAT048
and CAT062 with edition-aware specification registry, pcap and binary stream
readers, typed exceptions, pandas/Arrow/Polars/Parquet/GeoJSON exporters and
PySpark helpers.
