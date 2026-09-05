"""Command-line interface for pyasteryx.

Installed as the ``pyasteryx`` command. It exists so that the common jobs —
"what is in this capture?", "give me these tracks as CSV", "show me the live
feed" — need no Python at all::

    pyasteryx info
    pyasteryx stats capture.pcap
    pyasteryx decode capture.pcap --cat 62 --limit 10
    pyasteryx tracks capture.pcap --format csv -o tracks.csv
    pyasteryx listen 239.1.1.1:8600 --tracks

Every subcommand streams: output appears as records are decoded, and piping into
``head`` stops the decode rather than buffering a whole capture.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, TextIO

from pyasteryx import __version__
from pyasteryx.decoder import Decoder
from pyasteryx.exceptions import AsteryxError
from pyasteryx.models import Message
from pyasteryx.spec import SpecRegistry
from pyasteryx.track import Track, tracks

_PCAP_SUFFIXES = {".pcap", ".pcapng", ".cap"}


# --- helpers ------------------------------------------------------------------


def _json_default(value: Any) -> Any:
    """Render datetimes as ISO-8601; anything else as its string form."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _parse_editions(values: Optional[Sequence[str]]) -> Dict[int, str]:
    """Turn ``["62=1.18", "21=2.6"]`` into ``{62: "1.18", 21: "2.6"}``."""
    editions: Dict[int, str] = {}
    for raw in values or ():
        category, _, edition = raw.partition("=")
        if not edition:
            raise SystemExit(f"pyasteryx: --edition expects CAT=EDITION, got {raw!r}")
        try:
            editions[int(category)] = edition
        except ValueError:
            raise SystemExit(f"pyasteryx: --edition category must be a number, got {category!r}") from None
    return editions


def _parse_endpoint(raw: str) -> tuple[Optional[str], int]:
    """Parse ``"239.1.1.1:8600"`` or a bare ``"8600"`` into ``(group, port)``."""
    group, sep, port_text = raw.rpartition(":")
    if not sep:
        group, port_text = "", raw
    try:
        port = int(port_text)
    except ValueError:
        raise SystemExit(f"pyasteryx: could not read a port from {raw!r}") from None
    return (group or None), port


def _read_messages(decoder: Decoder, source: str) -> Iterator[Message]:
    """Stream messages from a path, choosing pcap or raw framing by suffix.

    ``-`` reads raw ASTERIX from standard input.
    """
    if source == "-":
        return decoder.iter_stream(sys.stdin.buffer)
    path = Path(source)
    if not path.exists():
        raise SystemExit(f"pyasteryx: no such file: {source}")
    if path.suffix.lower() in _PCAP_SUFFIXES:
        return decoder.iter_pcap(path)
    return decoder.iter_file(path)


def _filtered(
    messages: Iterable[Message],
    categories: Optional[Sequence[int]],
    limit: Optional[int],
) -> Iterator[Message]:
    """Apply the ``--cat`` and ``--limit`` filters to a message stream."""
    wanted = set(categories) if categories else None
    count = 0
    for message in messages:
        if wanted is not None and message.category not in wanted:
            continue
        yield message
        count += 1
        if limit is not None and count >= limit:
            return


def _open_output(path: Optional[str]) -> TextIO:
    """Return the output stream for ``-o``, defaulting to stdout."""
    if path is None or path == "-":
        return sys.stdout
    return open(path, "w", encoding="utf-8", newline="")


# --- writers ------------------------------------------------------------------


def _write_jsonl(rows: Iterable[Dict[str, Any]], out: TextIO) -> int:
    count = 0
    for row in rows:
        out.write(json.dumps(row, default=_json_default))
        out.write("\n")
        count += 1
    return count


def _write_json(rows: Iterable[Dict[str, Any]], out: TextIO) -> int:
    materialised = list(rows)
    json.dump(materialised, out, default=_json_default, indent=2)
    out.write("\n")
    return len(materialised)


def _write_csv(rows: Iterable[Dict[str, Any]], out: TextIO, columns: Optional[List[str]]) -> int:
    """Write CSV. With no fixed ``columns``, the first row defines the header.

    Rows are streamed, so a later row carrying a key the first one lacked would
    have nowhere to go; those extra keys are dropped rather than shifting the
    columns. ``tracks`` passes an explicit, stable column list for this reason.
    """
    iterator = iter(rows)
    first = next(iterator, None)
    if first is None:
        return 0
    fieldnames = columns if columns is not None else list(first.keys())
    writer = csv.DictWriter(out, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerow(first)
    count = 1
    for row in iterator:
        writer.writerow(row)
        count += 1
    return count


def _write_rows(
    rows: Iterable[Dict[str, Any]],
    fmt: str,
    out: TextIO,
    columns: Optional[List[str]] = None,
) -> int:
    if fmt == "jsonl":
        return _write_jsonl(rows, out)
    if fmt == "json":
        return _write_json(rows, out)
    if fmt == "csv":
        return _write_csv(rows, out, columns)
    raise SystemExit(f"pyasteryx: unknown format {fmt!r}")


# --- subcommands --------------------------------------------------------------


def _cmd_info(args: argparse.Namespace) -> int:
    """List the bundled category specifications."""
    registry = SpecRegistry.with_bundled()
    print(f"pyasteryx {__version__}")
    print()
    print(f"{'CATEGORY':<10} {'EDITIONS':<20} NAME")
    for category in sorted(registry.categories()):
        editions = registry.editions(category)
        spec = registry.get(category)
        marked = [f"{e}*" if e == registry.latest_edition(category) else e for e in editions]
        print(f"CAT{category:03d}{'':<3} {', '.join(marked):<20} {spec.name}")
    print()
    print("* = default edition when none is pinned with --edition CAT=EDITION")
    return 0


def _cmd_stats(args: argparse.Namespace) -> int:
    """Summarise what a capture contains, without printing every record."""
    decoder = Decoder(editions=_parse_editions(args.edition), on_error="skip")
    per_category: Dict[int, int] = {}
    per_source: Dict[tuple, int] = {}
    track_numbers: set = set()
    first_time: Optional[float] = None
    last_time: Optional[float] = None
    total = 0

    for message in _read_messages(decoder, args.source):
        total += 1
        per_category[message.category] = per_category.get(message.category, 0) + 1
        sid = message.items.get(f"I{message.category:03d}/010")
        if isinstance(sid, dict) and "SAC" in sid and "SIC" in sid:
            key = (message.category, sid["SAC"], sid["SIC"])
            per_source[key] = per_source.get(key, 0) + 1
        if message.category == 62:
            track = Track(message)
            number = track.track_number
            if number is not None:
                track_numbers.add(number)
            tot = track.time_of_track
            if tot is not None:
                first_time = tot if first_time is None else min(first_time, tot)
                last_time = tot if last_time is None else max(last_time, tot)

    print(f"source            {args.source}")
    print(f"records           {total}")
    if decoder.errors:
        print(f"blocks skipped    {decoder.errors}")
    print()
    print("by category:")
    for category in sorted(per_category):
        print(f"  CAT{category:03d}          {per_category[category]}")
    if per_source:
        print()
        print("by source (SAC/SIC):")
        for (category, sac, sic), count in sorted(per_source.items()):
            print(f"  CAT{category:03d} {sac:>3}/{sic:<3}   {count}")
    if track_numbers:
        print()
        print(f"distinct tracks   {len(track_numbers)}")
    if first_time is not None and last_time is not None:
        span = last_time - first_time
        print(f"time of day span  {_hms(first_time)} .. {_hms(last_time)}  ({span:.1f} s)")
    return 0


def _hms(seconds: float) -> str:
    """Format seconds-since-midnight as ``HH:MM:SS.mmm``."""
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{int(hours):02d}:{int(minutes):02d}:{secs:06.3f}"


def _cmd_decode(args: argparse.Namespace) -> int:
    """Decode a capture to raw, item-keyed rows."""
    decoder = Decoder(
        editions=_parse_editions(args.edition),
        on_error="skip" if args.skip_errors else "raise",
    )
    messages = _filtered(_read_messages(decoder, args.source), args.cat, args.limit)
    out = _open_output(args.output)
    try:
        count = _write_rows((m.to_dict() for m in messages), args.format, out)
    finally:
        if out is not sys.stdout:
            out.close()
    if args.output and args.output != "-":
        print(f"wrote {count} records to {args.output}", file=sys.stderr)
    return 0


#: Stable column order for ``tracks`` output, so CSV headers do not shift
#: between captures that happen to carry different optional items.
TRACK_COLUMNS: List[str] = list(Track(Message(62, {})).to_dict().keys())


def _cmd_tracks(args: argparse.Namespace) -> int:
    """Decode a capture to flat, named CAT062 track rows."""
    decoder = Decoder(
        editions=_parse_editions(args.edition),
        on_error="skip" if args.skip_errors else "raise",
    )
    day = date.fromisoformat(args.day) if args.day else None
    messages = _filtered(_read_messages(decoder, args.source), [62], args.limit)
    rows = _track_rows(messages, day=day, resolve_day=args.resolve_day, callsign=args.callsign)
    out = _open_output(args.output)
    try:
        count = _write_rows(rows, args.format, out, columns=TRACK_COLUMNS)
    finally:
        if out is not sys.stdout:
            out.close()
    if args.output and args.output != "-":
        print(f"wrote {count} track records to {args.output}", file=sys.stderr)
    return 0


def _track_rows(
    messages: Iterable[Message],
    day: Optional[date],
    resolve_day: bool,
    callsign: Optional[str],
) -> Iterator[Dict[str, Any]]:
    """Yield flat track rows, optionally keeping only one callsign."""
    wanted = callsign.upper() if callsign else None
    for track in tracks(messages, day=day, resolve_day=resolve_day):
        if wanted is not None and (track.callsign or "").upper() != wanted:
            continue
        yield track.to_dict()


def _cmd_listen(args: argparse.Namespace) -> int:
    """Decode a live UDP/multicast feed to stdout until interrupted."""
    decoder = Decoder(editions=_parse_editions(args.edition), on_error="skip")
    group, port = _parse_endpoint(args.endpoint)
    messages = _filtered(
        decoder.iter_udp(
            port,
            group=group,
            iface=args.iface,
            timeout=args.timeout,
            max_datagrams=args.max_datagrams,
        ),
        args.cat,
        args.limit,
    )

    where = f"{group}:{port}" if group else f"*:{port}"
    print(f"listening on {where} (ctrl-c to stop)", file=sys.stderr)

    if args.tracks:
        rows: Iterable[Dict[str, Any]] = _track_rows(
            messages, day=None, resolve_day=True, callsign=args.callsign
        )
    else:
        rows = (m.to_dict() for m in messages)

    count = 0
    try:
        for row in rows:
            sys.stdout.write(json.dumps(row, default=_json_default))
            sys.stdout.write("\n")
            sys.stdout.flush()  # a live feed is watched, so do not buffer
            count += 1
    except KeyboardInterrupt:
        pass
    print(f"\n{count} records, {decoder.errors} blocks skipped", file=sys.stderr)
    return 0


# --- argument parsing ---------------------------------------------------------


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--edition",
        action="append",
        metavar="CAT=EDITION",
        help="pin a category to an edition, e.g. --edition 62=1.18 (repeatable)",
    )


def _add_output(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-f",
        "--format",
        choices=("jsonl", "json", "csv"),
        default="jsonl",
        help="output format (default: jsonl, one JSON object per line)",
    )
    parser.add_argument("-o", "--output", metavar="PATH", help="write to a file instead of stdout")
    parser.add_argument("-n", "--limit", type=int, metavar="N", help="stop after N records")


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser."""
    parser = argparse.ArgumentParser(
        prog="pyasteryx",
        description="Decode EUROCONTROL ASTERIX surveillance data.",
    )
    parser.add_argument("--version", action="version", version=f"pyasteryx {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    info = subparsers.add_parser("info", help="list the bundled category specifications")
    info.set_defaults(func=_cmd_info)

    stats = subparsers.add_parser("stats", help="summarise the contents of a capture")
    stats.add_argument("source", help="a .pcap capture, a raw ASTERIX file, or - for stdin")
    _add_common(stats)
    stats.set_defaults(func=_cmd_stats)

    decode = subparsers.add_parser("decode", help="decode a capture to raw item-keyed records")
    decode.add_argument("source", help="a .pcap capture, a raw ASTERIX file, or - for stdin")
    decode.add_argument(
        "--cat", type=int, action="append", metavar="N", help="keep only this category (repeatable)"
    )
    decode.add_argument(
        "--skip-errors", action="store_true", help="skip malformed data blocks instead of failing"
    )
    _add_common(decode)
    _add_output(decode)
    decode.set_defaults(func=_cmd_decode)

    trk = subparsers.add_parser("tracks", help="decode CAT062 to flat, named track rows")
    trk.add_argument("source", help="a .pcap capture, a raw ASTERIX file, or - for stdin")
    trk.add_argument("--day", metavar="YYYY-MM-DD", help="UTC date to anchor timestamps on")
    trk.add_argument(
        "--resolve-day",
        action="store_true",
        help="follow the midnight wrap, for captures crossing 00:00 UTC",
    )
    trk.add_argument("--callsign", metavar="ID", help="keep only this callsign")
    trk.add_argument(
        "--skip-errors", action="store_true", help="skip malformed data blocks instead of failing"
    )
    _add_common(trk)
    _add_output(trk)
    trk.set_defaults(func=_cmd_tracks)

    listen = subparsers.add_parser("listen", help="decode a live UDP or multicast feed")
    listen.add_argument("endpoint", help="GROUP:PORT for multicast, or PORT for unicast")
    listen.add_argument(
        "--iface", default="0.0.0.0", metavar="ADDR", help="local interface for the multicast join"
    )
    listen.add_argument(
        "--tracks", action="store_true", help="emit flat CAT062 track rows instead of raw records"
    )
    listen.add_argument("--callsign", metavar="ID", help="with --tracks, keep only this callsign")
    listen.add_argument(
        "--cat", type=int, action="append", metavar="N", help="keep only this category (repeatable)"
    )
    listen.add_argument(
        "--timeout", type=float, metavar="SEC", help="stop after this long with no datagram"
    )
    listen.add_argument(
        "--max-datagrams", type=int, metavar="N", help="stop after this many datagrams"
    )
    listen.add_argument("-n", "--limit", type=int, metavar="N", help="stop after N records")
    _add_common(listen)
    listen.set_defaults(func=_cmd_listen)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point for the ``pyasteryx`` command."""
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except BrokenPipeError:
        # `pyasteryx decode big.pcap | head` closes the pipe under us. Python
        # flushes stdout again at shutdown and would raise a second time, so
        # point the fd at devnull to make that final flush a no-op.
        _silence_stdout()
        return 0
    except KeyboardInterrupt:  # pragma: no cover - interactive
        return 130
    except AsteryxError as exc:
        print(f"pyasteryx: {exc}", file=sys.stderr)
        return 1


def _silence_stdout() -> None:
    """Redirect stdout to devnull so the interpreter's exit flush cannot raise."""
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
    except (OSError, ValueError):  # pragma: no cover - stdout may not have an fd
        pass


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
