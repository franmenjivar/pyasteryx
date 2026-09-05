"""A typed, physical-units view over CAT062 system-track records.

Raw ASTERIX decoding gives you nested dictionaries keyed by item id::

    msg["I062/380"]["ID"]["ACID"]      # 'DLH4AB'
    msg["I062/185"]["Vx"]              # 123.75   (m/s, cartesian east)

That is faithful to the standard and useless in an analysis notebook. A
:class:`Track` wraps one CAT062 record and exposes what a surveillance engineer
actually asks for — callsign, position, ground speed in knots, vertical rate in
feet per minute, track lifecycle flags — resolving each from whichever data item
happens to carry it in that particular record.

Nothing is copied: a :class:`Track` holds a reference to its
:class:`~pyasteryx.models.Message` and computes properties on access, so wrapping
a whole feed costs one small object per record.

Example::

    from pyasteryx import Decoder, tracks

    for trk in tracks(Decoder().iter_pcap("feed.pcap")):
        if trk.callsign and trk.ground_speed_kt:
            print(trk.track_number, trk.callsign, round(trk.ground_speed_kt))
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

from pyasteryx.enums import describe
from pyasteryx.models import Message
from pyasteryx.timing import DayResolver, to_datetime

__all__ = ["Track", "tracks", "group_by_track"]

CAT062 = 62

# I062/380/GSP carries ground speed with an LSB of 2^-14 NM/s.
_NM_PER_S_TO_KT = 3600.0
# I062/185 velocities are metres per second.
_MS_TO_KT = 3600.0 / 1852.0
# I062/136 / I062/380 altitudes are already scaled to feet; a flight level is
# hundreds of feet.
_FT_PER_FL = 100.0


@dataclass(frozen=True, slots=True)
class Track:
    """One CAT062 system-track record, presented in engineering units.

    Every property returns ``None`` when the underlying data item is absent from
    the record, which is the normal case — a CAT062 feed sends a partial update
    for most records and only occasionally a full one.

    Attributes:
        message: The wrapped :class:`~pyasteryx.models.Message`.
        day: Optional UTC date used to turn :attr:`time_of_track` into an
            absolute :attr:`timestamp`.
    """

    message: Message
    day: Optional[date] = None

    # -- Identity ----------------------------------------------------------

    @property
    def sac(self) -> Optional[int]:
        """System Area Code of the emitting system (I062/010)."""
        return self._field("I062/010", "SAC")

    @property
    def sic(self) -> Optional[int]:
        """System Identification Code of the emitting system (I062/010)."""
        return self._field("I062/010", "SIC")

    @property
    def source(self) -> Optional[Tuple[int, int]]:
        """``(SAC, SIC)`` of the emitting system, or ``None``."""
        sac, sic = self.sac, self.sic
        return None if sac is None or sic is None else (sac, sic)

    @property
    def track_number(self) -> Optional[int]:
        """Track number assigned by the tracker (I062/040).

        This is the key you group on to reconstruct a trajectory. It is unique
        only within one emitting system, so pair it with :attr:`source` when
        merging feeds.
        """
        return self._field("I062/040", "TrkN")

    @property
    def callsign(self) -> Optional[str]:
        """Target identification / callsign (I062/380 ID), trailing blanks stripped."""
        value = self._sub("I062/380", "ID", "ACID")
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return None

    @property
    def address(self) -> Optional[str]:
        """24-bit ICAO aircraft address as uppercase hex (I062/380 ADR)."""
        return self._sub("I062/380", "ADR", "ADR")

    @property
    def mode_3a(self) -> Optional[str]:
        """Mode 3/A squawk as a 4-digit octal string (I062/060)."""
        return self._field("I062/060", "Mode3A")

    @property
    def mode_3a_valid(self) -> Optional[bool]:
        """Whether the Mode 3/A code was validated (I062/060 V == 0)."""
        v = self._field("I062/060", "V")
        return None if v is None else v == 0

    # -- Time --------------------------------------------------------------

    @property
    def time_of_track(self) -> Optional[float]:
        """Time of track information, in seconds since midnight UTC (I062/070)."""
        return self._field("I062/070", "ToT")

    @property
    def timestamp(self) -> Optional[datetime]:
        """Absolute UTC datetime, or ``None`` if :attr:`day` was not supplied.

        ASTERIX carries no date, so this needs the recording's UTC day. Pass it
        via :func:`tracks` (``day=...``), or use a
        :class:`~pyasteryx.timing.DayResolver` for feeds crossing midnight.
        """
        tot = self.time_of_track
        if tot is None or self.day is None:
            return None
        return to_datetime(tot, self.day)

    # -- Position ----------------------------------------------------------

    @property
    def latitude(self) -> Optional[float]:
        """WGS-84 latitude in degrees (I062/105)."""
        return self._field("I062/105", "Lat")

    @property
    def longitude(self) -> Optional[float]:
        """WGS-84 longitude in degrees (I062/105)."""
        return self._field("I062/105", "Lon")

    @property
    def position(self) -> Optional[Tuple[float, float]]:
        """``(latitude, longitude)`` in degrees, or ``None`` if not in this record."""
        lat, lon = self.latitude, self.longitude
        return None if lat is None or lon is None else (lat, lon)

    @property
    def cartesian(self) -> Optional[Tuple[float, float]]:
        """``(x, y)`` position in metres in the system cartesian frame (I062/100)."""
        x = self._field("I062/100", "X")
        y = self._field("I062/100", "Y")
        return None if x is None or y is None else (x, y)

    # -- Altitude ----------------------------------------------------------

    @property
    def measured_altitude_ft(self) -> Optional[float]:
        """Last measured barometric altitude in feet (I062/136)."""
        return self._field("I062/136", "MFL")

    @property
    def flight_level(self) -> Optional[float]:
        """Last measured barometric altitude expressed as a flight level (I062/136)."""
        alt = self.measured_altitude_ft
        return None if alt is None else alt / _FT_PER_FL

    @property
    def geometric_altitude_ft(self) -> Optional[float]:
        """Geometric (GNSS) altitude in feet (I062/130)."""
        return self._field("I062/130", "Alt")

    @property
    def selected_altitude_ft(self) -> Optional[float]:
        """Selected / target altitude in feet from aircraft-derived data (I062/380 SAL)."""
        return self._sub("I062/380", "SAL", "Alt")

    @property
    def barometric_pressure_setting(self) -> Optional[float]:
        """Barometric pressure setting in mb, offset from 800 mb (I062/380 BPS)."""
        return self._sub("I062/380", "BPS", "BPS")

    # -- Motion ------------------------------------------------------------

    @property
    def velocity_ms(self) -> Optional[Tuple[float, float]]:
        """``(Vx, Vy)`` cartesian velocity in metres per second (I062/185)."""
        vx = self._field("I062/185", "Vx")
        vy = self._field("I062/185", "Vy")
        return None if vx is None or vy is None else (vx, vy)

    @property
    def ground_speed_kt(self) -> Optional[float]:
        """Ground speed in knots.

        Prefers the aircraft-derived value (I062/380 GSP) when present, otherwise
        derives it from the calculated cartesian velocity (I062/185).
        """
        gsp = self._sub("I062/380", "GSP", "GS")
        if gsp is not None:
            return gsp * _NM_PER_S_TO_KT
        velocity = self.velocity_ms
        if velocity is None:
            return None
        return math.hypot(velocity[0], velocity[1]) * _MS_TO_KT

    @property
    def track_angle_deg(self) -> Optional[float]:
        """Track angle in degrees true, in ``[0, 360)``.

        Prefers the aircraft-derived true track angle (I062/380 TAN), otherwise
        derives it from the cartesian velocity (I062/185), where ``Vx`` is the
        easterly and ``Vy`` the northerly component.
        """
        tan = self._sub("I062/380", "TAN", "TAN")
        if tan is not None:
            return tan % 360.0
        velocity = self.velocity_ms
        if velocity is None:
            return None
        vx, vy = velocity
        if vx == 0.0 and vy == 0.0:
            return None
        return math.degrees(math.atan2(vx, vy)) % 360.0

    @property
    def magnetic_heading_deg(self) -> Optional[float]:
        """Magnetic heading in degrees (I062/380 MHG)."""
        mah = self._sub("I062/380", "MHG", "MAH")
        return None if mah is None else mah % 360.0

    @property
    def vertical_rate_fpm(self) -> Optional[float]:
        """Rate of climb/descent in feet per minute.

        Prefers the calculated value (I062/220), falling back to the
        aircraft-derived barometric then geometric vertical rate (I062/380).
        """
        roc = self._field("I062/220", "RoC")
        if roc is not None:
            return roc
        bvr = self._sub("I062/380", "BVR", "BVR")
        if bvr is not None:
            return bvr
        return self._sub("I062/380", "GVR", "GVR")

    @property
    def indicated_airspeed(self) -> Optional[float]:
        """Indicated airspeed (I062/380 IAS); units depend on the IM flag."""
        return self._sub("I062/380", "IAS", "AS")

    @property
    def true_airspeed_kt(self) -> Optional[float]:
        """True airspeed in knots (I062/380 TAS)."""
        return self._sub("I062/380", "TAS", "TAS")

    @property
    def mach(self) -> Optional[float]:
        """Mach number (I062/380 MAC)."""
        return self._sub("I062/380", "MAC", "MNO")

    @property
    def rate_of_turn(self) -> Optional[float]:
        """Rate of turn in degrees per second (I062/380 TAR)."""
        return self._sub("I062/380", "TAR", "RoT")

    # -- Lifecycle and status ----------------------------------------------

    @property
    def is_first_report(self) -> Optional[bool]:
        """First report of this track (I062/080 TSB) — the track was just created."""
        return self._flag("I062/080", "TSB")

    @property
    def is_last_report(self) -> Optional[bool]:
        """Last report of this track (I062/080 TSE) — the track number is now free."""
        return self._flag("I062/080", "TSE")

    @property
    def is_confirmed(self) -> Optional[bool]:
        """Confirmed track, as opposed to one still in initialisation (I062/080 CNF)."""
        cnf = self._field("I062/080", "CNF")
        return None if cnf is None else cnf == 0

    @property
    def is_simulated(self) -> Optional[bool]:
        """Simulated rather than live track (I062/080 SIM)."""
        return self._flag("I062/080", "SIM")

    @property
    def is_monosensor(self) -> Optional[bool]:
        """Track maintained from a single sensor (I062/080 MON)."""
        return self._flag("I062/080", "MON")

    @property
    def is_coasting(self) -> Optional[bool]:
        """No fresh position: the age of at least one position exceeds the system
        threshold (I062/080 CST)."""
        return self._flag("I062/080", "CST")

    @property
    def on_ground(self) -> Optional[bool]:
        """Surface target (I062/080 SFC)."""
        return self._flag("I062/080", "SFC")

    @property
    def spi(self) -> Optional[bool]:
        """Special Position Identification active (I062/080 SPI)."""
        return self._flag("I062/080", "SPI")

    @property
    def flight_plan_correlated(self) -> Optional[bool]:
        """Track correlated to a flight plan (I062/080 FPC)."""
        return self._flag("I062/080", "FPC")

    @property
    def emergency(self) -> Optional[str]:
        """Emergency status as text (I062/080 EMS), ``None`` when not emergency.

        Returns ``None`` both when the field is absent and when it reads
        "no emergency", so a truthy value always means a real condition.
        """
        ems = self._field("I062/080", "EMS")
        if not ems:  # absent, or 0 == no emergency
            return None
        return describe(CAT062, "I062/080", "EMS", ems)

    @property
    def altitude_source(self) -> Optional[str]:
        """Where the track's altitude came from, as text (I062/080 SRC)."""
        return describe(CAT062, "I062/080", "SRC", self._field("I062/080", "SRC"))

    @property
    def vertical_mode(self) -> Optional[str]:
        """Vertical mode of movement as text: level / climb / descent (I062/200 VERTA)."""
        return describe(CAT062, "I062/200", "VERTA", self._field("I062/200", "VERTA"))

    @property
    def transversal_mode(self) -> Optional[str]:
        """Transversal mode of movement as text: straight / left / right (I062/200 TRANSA)."""
        return describe(CAT062, "I062/200", "TRANSA", self._field("I062/200", "TRANSA"))

    @property
    def longitudinal_mode(self) -> Optional[str]:
        """Longitudinal acceleration mode as text (I062/200 LONGA)."""
        return describe(CAT062, "I062/200", "LONGA", self._field("I062/200", "LONGA"))

    @property
    def emitter_category(self) -> Optional[str]:
        """Aircraft emitter category as text (I062/380 EMC)."""
        return describe(CAT062, "I062/380", "ECAT", self._sub("I062/380", "EMC", "ECAT"))

    @property
    def contributing_sensors(self) -> Tuple[str, ...]:
        """Sensor types that have contributed an update, from the track ages (I062/290).

        Returns a tuple such as ``("SSR", "MDS", "ADS")``. Empty when I062/290 is
        absent from the record.
        """
        ages = self.message.get("I062/290")
        if not isinstance(ages, dict):
            return ()
        return tuple(key for key in ("PSR", "SSR", "MDS", "ADS", "ES", "VDL", "UAT", "LOP", "MLT") if key in ages)

    @property
    def update_ages(self) -> Dict[str, float]:
        """Per-sensor age of the last contributing update, in seconds (I062/290)."""
        ages = self.message.get("I062/290")
        if not isinstance(ages, dict):
            return {}
        out: Dict[str, float] = {}
        for key, value in ages.items():
            if isinstance(value, dict) and key in value:
                out[key] = value[key]
        return out

    # -- Conversion --------------------------------------------------------

    def to_dict(self, include_raw: bool = False) -> Dict[str, Any]:
        """Return a flat row of the named, physical-units attributes.

        This is the shape you want in a DataFrame: stable column names,
        engineering units, and ``None`` for anything absent from the record.

        Args:
            include_raw: Also merge in the raw dotted item/field keys from
                :meth:`Message.to_dict`, for fields this view does not surface.
        """
        row: Dict[str, Any] = {
            "timestamp": self.timestamp,
            "time_of_track": self.time_of_track,
            "sac": self.sac,
            "sic": self.sic,
            "track_number": self.track_number,
            "callsign": self.callsign,
            "address": self.address,
            "mode_3a": self.mode_3a,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "flight_level": self.flight_level,
            "measured_altitude_ft": self.measured_altitude_ft,
            "geometric_altitude_ft": self.geometric_altitude_ft,
            "selected_altitude_ft": self.selected_altitude_ft,
            "ground_speed_kt": self.ground_speed_kt,
            "track_angle_deg": self.track_angle_deg,
            "magnetic_heading_deg": self.magnetic_heading_deg,
            "vertical_rate_fpm": self.vertical_rate_fpm,
            "true_airspeed_kt": self.true_airspeed_kt,
            "mach": self.mach,
            "rate_of_turn": self.rate_of_turn,
            "vertical_mode": self.vertical_mode,
            "transversal_mode": self.transversal_mode,
            "emitter_category": self.emitter_category,
            "altitude_source": self.altitude_source,
            "emergency": self.emergency,
            "on_ground": self.on_ground,
            "spi": self.spi,
            "is_simulated": self.is_simulated,
            "is_confirmed": self.is_confirmed,
            "is_coasting": self.is_coasting,
            "is_first_report": self.is_first_report,
            "is_last_report": self.is_last_report,
            "flight_plan_correlated": self.flight_plan_correlated,
        }
        if include_raw:
            raw = self.message.to_dict()
            raw.pop("category", None)
            row.update(raw)
        return row

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        bits = [f"track={self.track_number}"]
        if self.callsign:
            bits.append(f"callsign={self.callsign!r}")
        pos = self.position
        if pos:
            bits.append(f"pos=({pos[0]:.4f},{pos[1]:.4f})")
        fl = self.flight_level
        if fl is not None:
            bits.append(f"FL{fl:.0f}")
        return f"<Track {' '.join(bits)}>"

    # -- Internals ---------------------------------------------------------

    def _field(self, item_id: str, name: str) -> Any:
        """Return ``items[item_id][name]``, or ``None`` if either is absent."""
        item = self.message.items.get(item_id)
        if isinstance(item, dict):
            return item.get(name)
        return None

    def _sub(self, item_id: str, subfield: str, name: str) -> Any:
        """Return a field nested inside a compound item's subfield, or ``None``."""
        item = self.message.items.get(item_id)
        if not isinstance(item, dict):
            return None
        sub = item.get(subfield)
        if isinstance(sub, dict):
            return sub.get(name)
        return None

    def _flag(self, item_id: str, name: str) -> Optional[bool]:
        """Return a one-bit field as a bool, or ``None`` if absent."""
        value = self._field(item_id, name)
        return None if value is None else bool(value)


def tracks(
    messages: Iterable[Message],
    day: Optional[date] = None,
    resolve_day: bool = False,
) -> Iterator[Track]:
    """Wrap every CAT062 record in an iterable as a :class:`Track`.

    Non-CAT062 messages are skipped, so this composes directly with a decoder
    reading a mixed feed.

    Args:
        messages: Any iterable of decoded messages.
        day: UTC date to anchor :attr:`Track.timestamp` on.
        resolve_day: Track the midnight wrap with a
            :class:`~pyasteryx.timing.DayResolver`, starting from ``day``
            (or today, UTC). Use this for feeds that run across midnight.

    Yields:
        One :class:`Track` per CAT062 record, lazily.
    """
    if resolve_day:
        resolver = DayResolver(day)
        for message in messages:
            if message.category != CAT062:
                continue
            item = message.items.get("I062/070")
            if isinstance(item, dict) and "ToT" in item:
                resolver.resolve(item["ToT"])
            yield Track(message, resolver.day)
        return

    for message in messages:
        if message.category == CAT062:
            yield Track(message, day)


def group_by_track(
    items: Iterable[Track],
    by_source: bool = True,
) -> Dict[Any, List[Track]]:
    """Group tracks into trajectories, keyed by track number.

    Args:
        items: The tracks to group, in delivery order.
        by_source: Key on ``(sac, sic, track_number)`` rather than the track
            number alone. Track numbers are only unique within one emitting
            system, so keep this on when merging several feeds.

    Returns:
        A dict mapping the key to the list of that track's records, each list in
        the order the records arrived.

    Note:
        This buffers every record in memory. For a large capture, filter first
        (by time window, region or callsign) or stream into storage instead.
    """
    out: Dict[Any, List[Track]] = {}
    for track in items:
        number = track.track_number
        if number is None:
            continue
        key: Any = (track.sac, track.sic, number) if by_source else number
        out.setdefault(key, []).append(track)
    return out
