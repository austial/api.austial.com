from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from austial import (
    BadRequestException,
    ConflictException,
    GoneException,
    Injectable,
    NotFoundException,
    ServiceUnavailableException,
    TooManyRequestsException,
)
from austial.orm import FindOptions, InjectRepository, Repository

from ..availability.service import AvailabilityService
from ..calendar.ics import build_ics
from ..calendar.provider import CalendarProvider, EventDetails
from ..entities import Booking, Hold
from ..mail import templates
from ..mail.mailer import Mailer, Message
from ..settings import Settings
from ..timeutil import as_utc, iso, now_utc, parse_iso, to_db
from .dto import HoldDto

logger = logging.getLogger("booking.service")

MAX_CODE_ATTEMPTS = 5
MAX_SENDS = 4
RESEND_COOLDOWN = timedelta(seconds=30)
MAX_PENDING_PER_EMAIL = 3


def format_when(start: datetime, tz_name: str) -> str:
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("UTC")
        tz_name = "UTC"
    local = as_utc(start).astimezone(tz)
    return f"{local.strftime('%A')}, {local.day} {local.strftime('%b %Y, %H:%M')} ({tz_name.replace('_', ' ')})"


def public_booking(b: Booking) -> dict:
    return {
        "id": b.id,
        "start": iso(b.start),
        "end": iso(b.end),
        "meetUrl": b.meet_url,
        "timezone": b.timezone,
        "status": b.status,
    }


@Injectable()
class BookingsService:
    def __init__(
        self,
        settings: Settings,
        availability: AvailabilityService,
        mailer: Mailer,
        calendar: CalendarProvider,
        holds: Repository[Hold] = InjectRepository(Hold),
        bookings: Repository[Booking] = InjectRepository(Booking),
    ):
        self.s = settings
        self.availability = availability
        self.mailer = mailer
        self.calendar = calendar
        self.holds = holds
        self.bookings = bookings
        self._lock = asyncio.Lock()

    # --- secrets -----------------------------------------------------------------------------------------------

    def _mac(self, purpose: str, value: str) -> str:
        return hmac.new(self.s.code_pepper.encode(), f"{purpose}:{value}".encode(), hashlib.sha256).hexdigest()

    def manage_token(self, booking_id: str) -> str:
        """Deterministic per booking, so reminders can rebuild the link without storing the raw token."""
        digest = hmac.new(self.s.code_pepper.encode(), f"manage:{booking_id}".encode(), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest).decode().rstrip("=")

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def manage_url(self, booking: Booking) -> str:
        return f"{self.s.site_url}/manage/{self.manage_token(booking.id)}"

    # --- holds and codes ---------------------------------------------------------------------------------------

    async def create_hold(self, dto: HoldDto) -> dict:
        try:
            start = parse_iso(dto.start)
        except ValueError as exc:
            raise BadRequestException("Invalid start time.") from exc
        try:
            ZoneInfo(dto.timezone)
            tz = dto.timezone
        except ZoneInfoNotFoundError:
            tz = "UTC"
        now = now_utc()
        code = f"{secrets.randbelow(10**6):06d}"
        async with self._lock:
            if not await self.availability.is_available(start):
                raise ConflictException("That time is no longer available.")
            pending = [
                h
                for h in await self.holds.find(FindOptions(where={"email": dto.email, "status": "pending"}))
                if as_utc(h.expires_at) > now
            ]
            if len(pending) >= MAX_PENDING_PER_EMAIL:
                raise TooManyRequestsException("Too many open holds for this email. Please wait a few minutes.")
            hold = Hold(
                id=secrets.token_urlsafe(12),
                start=to_db(start),
                end=to_db(start + self.availability.slot_length),
                timezone=tz,
                name=dto.name,
                email=dto.email,
                company=dto.company,
                company_type=dto.company_type,
                goal=dto.goal.strip(),
                code_hash=self._mac("code", code),
                attempts=0,
                sends=1,
                last_sent_at=to_db(now),
                expires_at=to_db(now + timedelta(minutes=self.s.hold_minutes)),
                status="pending",
                created_at=to_db(now),
            )
            await self.holds.insert(hold)
        try:
            await self.mailer.send(templates.code_email(hold.email, hold.name, code, format_when(start, tz), self.s.hold_minutes))
        except Exception as exc:
            logger.error("could not send code email: %r", exc)
            await self.holds.update({"id": hold.id}, {"status": "expired"})
            raise ServiceUnavailableException("We could not send the verification email. Please try again.") from exc
        return {"holdId": hold.id, "expiresAt": iso(hold.expires_at)}

    async def _pending_hold(self, hold_id: str) -> Hold:
        hold = await self.holds.find_one(FindOptions(where={"id": hold_id}))
        if hold is None:
            raise NotFoundException("Hold not found.")
        if hold.status != "pending":
            raise GoneException("This hold is no longer active.")
        if as_utc(hold.expires_at) <= now_utc():
            await self.holds.update({"id": hold.id}, {"status": "expired"})
            raise GoneException("Your hold expired. Please pick a time again.")
        return hold

    async def resend_code(self, hold_id: str) -> dict:
        hold = await self._pending_hold(hold_id)
        now = now_utc()
        if hold.sends >= MAX_SENDS:
            raise TooManyRequestsException("Too many codes sent. Please start again.")
        if now - as_utc(hold.last_sent_at) < RESEND_COOLDOWN:
            raise TooManyRequestsException("Please wait a moment before asking for another code.")
        code = f"{secrets.randbelow(10**6):06d}"
        await self.holds.update(
            {"id": hold.id},
            {"code_hash": self._mac("code", code), "attempts": 0, "sends": hold.sends + 1, "last_sent_at": to_db(now)},
        )
        await self.mailer.send(
            templates.code_email(hold.email, hold.name, code, format_when(hold.start, hold.timezone), self.s.hold_minutes)
        )
        return {"expiresAt": iso(hold.expires_at)}

    async def verify(self, hold_id: str, code: str) -> dict:
        hold = await self._pending_hold(hold_id)
        if hold.attempts >= MAX_CODE_ATTEMPTS:
            raise TooManyRequestsException("Too many wrong codes. Please start again.")
        if not hmac.compare_digest(hold.code_hash, self._mac("code", code)):
            await self.holds.update({"id": hold.id}, {"attempts": hold.attempts + 1})
            raise BadRequestException("That code is not correct.")

        async with self._lock:
            start = as_utc(hold.start)
            if not await self.availability.is_available(start, ignore_hold=hold.id):
                await self.holds.update({"id": hold.id}, {"status": "expired"})
                raise ConflictException("That time was just taken. Please pick another.")
            booking_id = secrets.token_urlsafe(10)
            booking = Booking(
                id=booking_id,
                hold_id=hold.id,
                start=hold.start,
                end=hold.end,
                timezone=hold.timezone,
                name=hold.name,
                email=hold.email,
                company=hold.company,
                company_type=hold.company_type,
                goal=hold.goal,
                token_hash=self._token_hash(self.manage_token(booking_id)),
                status="confirmed",
                event_id=None,
                meet_url=None,
                reminder_sent_at=None,
                created_at=to_db(now_utc()),
            )
            await self.bookings.insert(booking)
            await self.holds.update({"id": hold.id}, {"status": "confirmed"})

        try:
            result = await self.calendar.create_event(self._event(booking))
            booking.event_id, booking.meet_url = result.event_id, result.meet_url
            await self.bookings.update({"id": booking.id}, {"event_id": result.event_id, "meet_url": result.meet_url})
        except Exception as exc:  # noqa: BLE001 - the booking stands; the link follows
            logger.error("calendar event failed for booking %s: %r", booking.id, exc)
        await self._notify_booked(booking)
        return {"booking": public_booking(booking)}

    # --- helpers -----------------------------------------------------------------------------------------------

    def _event(self, b: Booking) -> EventDetails:
        return EventDetails(
            summary=f"Austial discovery call: {b.name} ({b.company})",
            description=f"{b.name}, {b.company} ({b.company_type})\n\nGoal:\n{b.goal}",
            start=as_utc(b.start),
            end=as_utc(b.end),
            timezone=b.timezone,
            attendee_email=b.email,
        )

    def _ics(self, b: Booking) -> str | None:
        if b.event_id:  # Google already emails the invite
            return None
        return build_ics(b.id, as_utc(b.start), as_utc(b.end), "Austial discovery call", b.meet_url, "no-reply@austial.com")

    async def _safe_send(self, message: Message) -> None:
        try:
            await self.mailer.send(message)
        except Exception as exc:  # noqa: BLE001
            logger.error("email to %s failed: %r", message.to, exc)

    async def _notify_booked(self, b: Booking) -> None:
        when = format_when(b.start, b.timezone)
        await self._safe_send(templates.confirmation_email(b.email, b.name, when, b.meet_url, self.manage_url(b), self._ics(b)))
        if self.s.mail_notify_to:
            rows = [("Name", b.name), ("Email", b.email), ("Company", f"{b.company} ({b.company_type})"), ("When", when), ("Goal", b.goal)]
            await self._safe_send(templates.owner_booking_email(self.s.mail_notify_to, rows, b.email))

    # --- manage links ------------------------------------------------------------------------------------------

    async def _by_token(self, token: str) -> Booking:
        found = await self.bookings.find_one(FindOptions(where={"token_hash": self._token_hash(token)}))
        if found is None:
            raise NotFoundException("Booking not found.")
        return found

    async def view(self, token: str) -> dict:
        b = await self._by_token(token)
        return {**public_booking(b), "name": b.name}

    async def cancel(self, token: str) -> dict:
        b = await self._by_token(token)
        if b.status == "cancelled":
            return public_booking(b)
        await self.bookings.update({"id": b.id}, {"status": "cancelled"})
        b.status = "cancelled"
        if b.event_id:
            try:
                await self.calendar.delete_event(b.event_id)
            except Exception as exc:  # noqa: BLE001
                logger.error("calendar delete failed for %s: %r", b.id, exc)
        await self._safe_send(templates.cancelled_email(b.email, b.name, format_when(b.start, b.timezone), self.s.site_url))
        return public_booking(b)

    async def reschedule(self, token: str, new_start: str) -> dict:
        b = await self._by_token(token)
        if b.status != "confirmed" or as_utc(b.start) <= now_utc():
            raise GoneException("This booking can no longer be changed.")
        try:
            start = parse_iso(new_start)
        except ValueError as exc:
            raise BadRequestException("Invalid start time.") from exc
        async with self._lock:
            if not await self.availability.is_available(start, ignore_booking=b.id):
                raise ConflictException("That time is no longer available.")
            end = start + self.availability.slot_length
            await self.bookings.update({"id": b.id}, {"start": to_db(start), "end": to_db(end), "reminder_sent_at": None})
            b.start, b.end, b.reminder_sent_at = to_db(start), to_db(end), None
        if b.event_id:
            try:
                await self.calendar.move_event(b.event_id, self._event(b))
            except Exception as exc:  # noqa: BLE001
                logger.error("calendar move failed for %s: %r", b.id, exc)
        await self._safe_send(
            templates.rescheduled_email(b.email, b.name, format_when(b.start, b.timezone), b.meet_url, self.manage_url(b), self._ics(b))
        )
        return public_booking(b)
