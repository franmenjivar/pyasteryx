# pyasteryx

A fast, dependency-free, **specification-driven** decoder for EUROCONTROL
**ASTERIX** surveillance data — built for Air Traffic Management research,
surveillance analytics and big-data (PySpark/Arrow) processing, with
**first-class CAT062 system-track support**.

```bash
pip install pyasteryx
```

```python
from pyasteryx import Decoder, tracks

for track in tracks(Decoder().iter_multicast("239.1.1.1", 8600)):
    print(track.callsign, track.flight_level, track.ground_speed_kt)
```

```
DLH4AB 350.0 388.8
BAW22  110.0 254.1
```

## Why another ASTERIX library?

Existing Python ASTERIX decoders stop at the wire format: they hand back nested
dictionaries of raw integers keyed by item id, and leave the rest to you.
pyasteryx goes the rest of the way.

|  | pyasteryx | typical alternatives |
|---|---|---|
| Live UDP / multicast feeds | **built in** | not supported |
| PCAP capture files | **built in**, streaming | manual packet extraction |
| Absolute UTC timestamps | **built in**, midnight-wrap aware | raw 1/128 s counter |
| Named fields in engineering units | **`Track` view** | `msg["I062/380"]["ID"]["ACID"]` |
| Coded fields as text | **built in** (`"triangulation"`) | raw integer (`3`) |
| Command-line tool | **`pyasteryx` command** | none |
| DataFrame / Parquet / GeoJSON export | **built in** | none |
| Multiple editions of a category | **bundled, pinnable** | one hardcoded edition |
| Error recovery on a dirty feed | **per-block skip + counter** | all-or-nothing |
| Runtime dependencies | **none** | varies |
| Install footprint | **70 KB wheel, 222 KB installed** | varies |

Editions bundled today:

| Category | Description | Editions |
|----------|-------------|----------|
| **CAT062** | **System Track Data** | 1.17, **1.18** |
| CAT021 | ADS-B Target Reports | 2.4, **2.6** |
| CAT048 | Monoradar Target Reports | **1.21** |

(Bold = default edition when none is pinned.)

## From the wire to a track

Here is one real CAT062 system-track record — 48 octets, exactly as it arrives in
a UDP datagram:

```
3E 00 30 9B 5F A4 19 C8 58 78 00 00 80 00 00 00
20 00 00 03 20 00 00 0F 11 C0 3C 6D A9 10 C2 34
04 28 20 04 D2 0D 30 B0 04 08 0C 04 05 78 01 00
```

Nothing in those bytes says where one field ends and the next begins. The layout
is carried by a bitmap (the FSPEC), and the meaning by the edition of the
standard you happen to be decoding against:

```
3E                       CAT = 62
00 30                    LEN = 48 octets, header included
9B 5F A4                 FSPEC — 3 octets of presence bits, FX-chained
   19 C8                 I062/010  data source identifier
   58 78 00              I062/070  time of track
   00 80 00 00 00 20 00 00   I062/105  position, WGS-84
   03 20 00 00           I062/185  cartesian velocity
   0F 11                 I062/060  Mode 3/A
   C0 3C 6D A9 10 C2 34 04 28 20   I062/380  aircraft-derived data
   04 D2                 I062/040  track number
   0D 30                 I062/080  track status (extended, 2 extents)
   B0 04 08 0C           I062/290  system track update ages (compound)
   04                    I062/200  mode of movement
   05 78                 I062/136  measured flight level
   01 00                 I062/220  rate of climb/descent
```

**Decoded the usual way**, you get the structure back, faithfully — and then you
are on your own:

```python
{
  "I062/010": {"SAC": 25, "SIC": 200},
  "I062/070": {"ToT": 45296.0},
  "I062/105": {"Lat": 45.0, "Lon": 11.25},
  "I062/185": {"Vx": 200.0, "Vy": 0.0},
  "I062/060": {"V": 0, "G": 0, "CH": 0, "Mode3A": "7421"},
  "I062/380": {"ADR": {"ADR": "3C6DA9"}, "ID": {"ACID": "DLH4AB"}},
  "I062/040": {"TrkN": 1234},
  "I062/080": {"MON": 0, "SPI": 0, "MRH": 0, "SRC": 3, "CNF": 0,
               "SIM": 0, "TSE": 0, "TSB": 1, "FPC": 1, "AFF": 0,
               "STP": 0, "KOS": 0},
  "I062/290": {"TRK": {"TRK": 1.0}, "SSR": {"SSR": 2.0}, "MDS": {"MDS": 3.0}},
  "I062/200": {"TRANSA": 0, "LONGA": 0, "VERTA": 1, "ADF": 0},
  "I062/136": {"MFL": 35000.0},
  "I062/220": {"RoC": 1600.0},
}
```

To get a ground speed out of that you must know that `Vx`/`Vy` are metres per
second in a cartesian frame and convert; to get a heading, that `Vx` is the
easterly component; to get a timestamp, that `ToT` is seconds since midnight UTC
and that the date is not in the message at all. `SRC: 3` and `VERTA: 1` mean
nothing without the specification open beside you.

**With pyasteryx**, the same 48 octets:

```python
from datetime import date
from pyasteryx import Decoder, tracks

t = next(tracks(Decoder().decode(raw), day=date(2026, 9, 5)))
```

```python
t.timestamp               datetime(2026, 9, 5, 12, 34, 56, tzinfo=utc)
t.track_number            1234
t.callsign                'DLH4AB'
t.address                 '3C6DA9'
t.mode_3a                 '7421'
t.position                (45.0, 11.25)
t.flight_level            350.0
t.measured_altitude_ft    35000.0
t.ground_speed_kt         388.76889848812095
t.track_angle_deg         90.0
t.vertical_rate_fpm       1600.0
t.vertical_mode           'climb'
t.transversal_mode        'constant course'
t.altitude_source         'triangulation'
t.is_confirmed            True
t.is_first_report         True     # this track was just created
t.is_last_report          False
t.flight_plan_correlated  True
t.contributing_sensors    ('SSR', 'MDS')
```

Same bytes, same fidelity — the raw items are still on `t.message` — but the
unit conversions, the missing date, and the code tables are done.


## The `Track` view

This is the part that saves the most time. A CAT062 record decodes to a nested
structure faithful to the standard and awkward to work with:

```python
msg["I062/380"]["ID"]["ACID"]     # 'DLH4AB'
msg["I062/185"]["Vx"]             # 123.75  — m/s, cartesian east
msg["I062/080"]["SRC"]            # 3       — meaning?
```

Wrapping it in a `Track` gives you what you actually wanted:

```python
from pyasteryx import Decoder, tracks
from datetime import date

for t in tracks(Decoder().iter_pcap("feed.pcap"), day=date(2026, 9, 5)):
    t.callsign            # 'DLH4AB'
    t.track_number        # 1234
    t.address             # '3C6DA9'   (24-bit ICAO)
    t.mode_3a             # '7421'     (octal squawk)
    t.timestamp           # datetime(2026, 9, 5, 12, 34, 56, tzinfo=utc)
    t.position            # (45.0, 11.25)
    t.flight_level        # 350.0
    t.ground_speed_kt     # 388.8
    t.track_angle_deg     # 90.0
    t.vertical_rate_fpm   # 1600.0
    t.vertical_mode       # 'climb'
    t.altitude_source     # 'triangulation'
    t.emergency           # None, or 'unlawful interference'
    t.is_first_report     # True  — this track was just created
    t.is_last_report      # False — track number about to be released
    t.contributing_sensors  # ('SSR', 'MDS')
```

Every property returns `None` when the record does not carry that item, which is
the normal case — a CAT062 feed sends mostly partial updates. Values are
resolved from whichever item carries them: `ground_speed_kt` prefers the
aircraft-derived I062/380 GSP and falls back to deriving it from the tracker's
I062/185 cartesian velocity.

`Track` holds a reference to its `Message` and computes on access, so wrapping a
whole feed costs one small object per record. The raw message is always there on
`track.message` if you need an item the view does not surface.

### Building trajectories

```python
from pyasteryx import Decoder, tracks, group_by_track

trajectories = group_by_track(tracks(Decoder().iter_pcap("feed.pcap")))
for (sac, sic, number), points in trajectories.items():
    print(number, len(points), points[0].callsign)
```

Track numbers are recycled and are only unique within one emitting system, so
the key includes the source by default.

## Reading data

Every source has an eager `decode_*` and a lazy `iter_*` twin. The lazy form
streams in constant memory, so captures larger than RAM are fine.

```python
from pyasteryx import Decoder

decoder = Decoder()

decoder.decode(raw_bytes)                    # bytes / bytearray / memoryview
decoder.decode_file("capture.bin")           # raw ASTERIX file
decoder.decode_pcap("capture.pcap")          # Ethernet/IPv4/UDP -> ASTERIX
decoder.decode_stream(open("f.bin", "rb"))   # any binary file-like

for msg in decoder.iter_pcap("huge.pcap"):   # constant memory
    ...
```

### Live feeds

CAT062 is normally distributed as UDP multicast. Point the decoder straight at
it — no socket setup, no packet reassembly:

```python
decoder = Decoder(on_error="skip")   # one bad datagram shouldn't end the session

for msg in decoder.iter_multicast("239.1.1.1", 8600, iface="10.0.0.5"):
    ...

for msg in decoder.iter_udp(8600):   # unicast
    ...
```

Set `iface` on a multi-homed host, otherwise the OS joins on the default route,
which is rarely the operational network. The reader raises `SO_RCVBUF` well
above the default, because a busy feed drops datagrams in the kernel *silently*.

## Timestamps

ASTERIX carries seconds-since-midnight-UTC and no date. Supply the day:

```python
from datetime import date
tracks(messages, day=date(2026, 9, 5))
```

For a feed running across midnight, let the resolver follow the wrap — otherwise
a trajectory jumps 24 hours backwards at 00:00:

```python
tracks(messages, resolve_day=True)
```

Or drive it yourself with `DayResolver`:

```python
from pyasteryx import DayResolver

resolver = DayResolver()
for msg in decoder.iter_multicast("239.1.1.1", 8600):
    ts = resolver.resolve(msg["I062/070"]["ToT"])
```

## Command line

```bash
pyasteryx info                                  # bundled categories and editions
pyasteryx stats capture.pcap                    # what's in this capture?
pyasteryx decode capture.pcap --cat 62 -n 10    # raw item-keyed records, as JSONL
pyasteryx tracks capture.pcap -f csv -o out.csv # flat named track rows
pyasteryx listen 239.1.1.1:8600 --tracks        # live feed to stdout
```

```
$ pyasteryx stats capture.pcap
source            capture.pcap
records           48213

by category:
  CAT062          48213

by source (SAC/SIC):
  CAT062  25/200    48213

distinct tracks   1197
time of day span  12:00:00.031 .. 12:59:59.968  (3599.9 s)
```

Everything streams, so `pyasteryx decode big.pcap | head` stops the decode
rather than buffering the capture. `-` reads raw ASTERIX from stdin.

## Exporting

Pass either raw messages or tracks — tracks give you named, engineering-unit
columns, which is usually what you want for analysis.

```python
from pyasteryx import Decoder, tracks
from pyasteryx.exporters import to_pandas, to_arrow, to_polars, to_parquet, to_geojson

points = tracks(Decoder().iter_pcap("feed.pcap"), day=date(2026, 9, 5))

df = to_pandas(points)
df.groupby("callsign")["flight_level"].max()

to_parquet(points, "tracks.parquet")
fc = to_geojson(points)          # FeatureCollection; position columns auto-detected
```

Install the optional dependencies with `pip install "pyasteryx[export]"`.

## PySpark

The decoder is pure Python and holds only immutable state, so it is safe to
broadcast and reuse across a partition.

```python
from pyasteryx.spark import asterix_decode_udf, decode_partition
from pyspark.sql.functions import col

# Vectorized (Arrow) pandas_udf: binary column -> JSON array of records
decode = asterix_decode_udf(editions={62: "1.18"})
df = df.withColumn("records", decode(col("payload")))

# Or RDD-style, one decoder per partition:
rows = df.rdd.mapPartitions(lambda it: decode_partition(it, "payload"))
```

Install with `pip install "pyasteryx[spark]"`.

## Editions

The ASTERIX wire format does not carry its edition, so you pin it per category.
Without a pin, the newest bundled edition is used.

```python
decoder = Decoder(editions={62: "1.18", 21: "2.4"})
```

```bash
pyasteryx decode capture.pcap --edition 62=1.17
```

## Error handling

By default a malformed block raises a typed exception. On a live feed or a field
recording you usually want to keep going:

```python
decoder = Decoder(on_error="skip")
messages = decoder.decode_pcap("dirty.pcap")
print(f"{decoder.errors} blocks skipped")
```

A block whose *header* framed correctly is skipped precisely — its declared
length still says where the next block starts, so only that block is lost. Only
an unreadable header forces the rest of the buffer to be abandoned.

All exceptions derive from `AsteryxError`:

```
AsteryxError
├── DecodeError
│   ├── TruncatedMessageError      buffer ended mid-message
│   ├── InvalidLengthError         impossible declared length
│   ├── InvalidFspecError          FSPEC malformed or never terminates
│   ├── UnsupportedCategoryError   no specification loaded for this category
│   └── UnsupportedItemError       FSPEC selects an item the spec doesn't define
├── SpecificationError             a specification file is malformed
├── PcapError                      unreadable pcap file
└── NetworkError                   feed socket could not be opened or joined
```

## Footprint

pyasteryx has no runtime dependencies and stays small enough to sit in a
container image or a Spark job without thought:

| | |
|---|---|
| Wheel (download) | **70 KB** |
| Installed on disk | **222 KB** |
| `import pyasteryx` | ~18 ms |
| `Decoder()` | **0.5 ms, 10 KiB** |
| First CAT062 record decoded | 2.2 ms, 105 KiB |

**Specifications load lazily.** `Decoder()` only indexes the bundled files —
their paths already encode the category and edition — and parses one when that
category is first decoded. A decoder on a CAT062 feed never pays for CAT021 or
CAT048, or for the older editions of CAT062. If you want everything parsed up
front (to validate every bundled file, say):

```python
from pyasteryx import SpecRegistry
from pyasteryx.spec import load_bundled_categories

registry = SpecRegistry(load_bundled_categories())
```

The bundled specification files are shipped minified, which is where over half
their on-disk size went. They are still plain JSON — inspect one with
`python -m json.tool`, or regenerate it readable with `tools/xml_to_spec.py
--pretty`.

## Architecture

Adding a category or edition is a data change, not a code change:

```
pyasteryx/
├── decoder.py     Public Decoder API (decode_* / iter_*)
├── track.py       CAT062 Track view: named, engineering units
├── timing.py      Time-of-day -> absolute UTC, midnight-wrap aware
├── enums.py       Coded-field meanings
├── cli.py         The `pyasteryx` command
├── io/            Byte sources: binary.py, pcap.py, net.py (streaming-first)
├── parser/        Category-agnostic structure: header, fspec, items, record
├── spec/          Data-driven definitions + edition-aware registry
│   └── data/catNNN/<edition>.json
├── exporters/     pandas / arrow / polars / parquet / geojson
└── spark.py       PySpark helpers (optional)
```

The `parser` layer contains no field meaning, and the public API is deliberately
frozen, so the parser can later be swapped for a Rust/PyO3 implementation
without users noticing.

Supported data-item encodings: fixed · extended (variable, multi-octet extents)
· repetitive · compound · explicit (RE/SP) · signed/unsigned · scaled · hex ·
octal · ASCII · 6-bit (IA5) characters.

### Regenerating or adding specifications

Specifications are converted from the authoritative
[CroatiaControlLtd/asterix](https://github.com/CroatiaControlLtd/asterix) XML
definitions — never hand-written:

```bash
python tools/xml_to_spec.py asterix_cat062_1_18.xml \
    src/pyasteryx/spec/data/cat062/1.18.json
```

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check .
```

## Non-goals

No GUI, no visualization, no ATM algorithms. pyasteryx focuses on decoding,
parsing, streaming, exporting and interoperability.

## License

MIT — see [LICENSE](LICENSE).
