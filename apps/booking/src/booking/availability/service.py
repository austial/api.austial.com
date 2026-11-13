from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from austial import Injectable, ServiceUnavailableException
from austial.orm import FindOptions, InjectRepository, Repository

from ..calendar.provider import CalendarProvider
from ..entities import Booking, Hold
from ..settings import Settings
from ..timeutil import as_utc, now_utc

logger = logging.getLogger("booking.availability")

DAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
APP_DIR = Path(__file__).resolve().parents[3]  # apps/booking


@dataclass(frozen=True)
class Window:
    days: frozenset[int]
    start: time
    end: time


@dataclass(frozen=True)
class AvailabilityConfig:
    tz: ZoneInfo
    slot_minutes: int
    buffer_minutes: int
    min_notice_hours: int
    max_days_ahead: int
    windows: tuple[Window, ...]


def load_config(path: str) -> AvailabilityConfig:
    file = Path(path)
    if not file.is_absolute():
        file = APP_DIR / file
    data = tomllib.loads(file.read_text())
    windows = tuple(
        Window(
            frozenset(DAYS[d.lower()[:3]] for d in w["days"]),
            time.fromisoformat(w["start"]),
            time.fromisoformat(w["end"]),
        )
        for w in data["hours"]
    )
    return AvailabilityConfig(
        tz=ZoneInfo(data.get("timezone", "UTC")),
        slot_minutes=int(data.get("slot_minutes", 30)),
        buffer_minutes=int(data.get("buffer_minutes", 0)),
        min_notice_hours=int(data.get("min_notice_hours", 0)),
        max_days_ahead=int(data.get("max_days_ahead", 30)),
        windows=windows,
    )


@dataclass(frozen=True)
class Slot:
    start: datetime
    end: datetime


@Injectable()
class AvailabilityService:
    """Open slots from the weekly hours, minus bookings, live holds and (if connected) your calendar."""

    def __init__(
        self,
        settings: Settings,
        calendar: CalendarProvider,
        holds: Repository[Hold] = InjectRepository(Hold),
        bookings: Repository[Booking] = InjectRepository(Booking),
    ):
        self.cfg = load_config(settings.availability_file)
        self.calendar = calendar
        self.holds = holds
        self.bookings = bookings

    @property
    def slot_length(self) -> timedelta:
        return timedelta(minutes=self.cfg.slot_minutes)

    def _candidates(self, start: datetime, end: datetime) -> list[Slot]:
        cfg = self.cfg
        out: list[Slot] = []
        day = start.astimezone(cfg.tz).date() - timedelta(days=1)
        last = end.astimezone(cfg.tz).date() + timedelta(days=1)
        while day <= last:
            for w in cfg.windows:
                if day.weekday() not in w.days:
                    continue
                cursor = datetime.combine(day, w.start, tzinfo=cfg.tz)
                close = datetime.combine(day, w.end, tzinfo=cfg.tz)
                while cursor + self.slot_length <= close:
                    s = as_utc(cursor)
                    out.append(Slot(s, s + self.slot_length))
                    cursor += self.slot_length
            day += timedelta(days=1)
        return out

    async def _busy(
        self, start: datetime, end: datetime, ignore_hold: str | None, ignore_booking: str | None
    ) -> list[tuple[datetime, datetime]]:
        now = now_utc()
        busy: list[tuple[datetime, datetime]] = []
        for b in await self.bookings.find(FindOptions(where={"status": "confirmed"})):
            if b.id != ignore_booking:
                busy.append((as_utc(b.start), as_utc(b.end)))
        for h in await self.holds.find(FindOptions(where={"status": "pending"})):
            if h.id != ignore_hold and as_utc(h.expires_at) > now:
                busy.append((as_utc(h.start), as_utc(h.end)))
        try:
            busy.extend(await self.calendar.busy(start - timedelta(days=1), end + timedelta(days=1)))
        except Exception as exc:
            logger.error("calendar free/busy failed: %r", exc)
            raise ServiceUnavailableException("Availability is temporarily unavailable.") from exc
        return busy

    async def slots(
        self,
        start: datetime,
        end: datetime,
        *,
        ignore_hold: str | None = None,
        ignore_booking: str | None = None,
    ) -> list[Slot]:
        cfg = self.cfg
        now = now_utc()
        earliest = now + timedelta(hours=cfg.min_notice_hours)
        latest = now + timedelta(days=cfg.max_days_ahead)
        lo, hi = max(as_utc(start), earliest), min(as_utc(end), latest)
        if lo >= hi:
            return []
        busy = await self._busy(lo, hi, ignore_hold, ignore_booking)
        gap = timedelta(minutes=cfg.buffer_minutes)
        result = []
        for s in self._candidates(lo, hi):
            if s.start < lo or s.start >= hi:
                continue
            if any(s.start < b_end + gap and s.end + gap > b_start for b_start, b_end in busy):
                continue
            result.append(s)
        return sorted(result, key=lambda x: x.start)

    async def is_available(
        self, start: datetime, *, ignore_hold: str | None = None, ignore_booking: str | None = None
    ) -> bool:
        start = as_utc(start)
        found = await self.slots(
            start, start + self.slot_length, ignore_hold=ignore_hold, ignore_booking=ignore_booking
        )
        return any(s.start == start for s in found)
