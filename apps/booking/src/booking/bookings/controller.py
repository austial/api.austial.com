from __future__ import annotations

from datetime import timedelta

from austial import BadRequestException, Body, Controller, Get, Post, Query, UseGuards
from austial.security import RateLimit, RateLimitGuard

from ..availability.service import AvailabilityService
from ..timeutil import iso, now_utc, parse_iso
from .dto import HoldDto, RescheduleDto, VerifyDto
from .service import BookingsService

MAX_RANGE = timedelta(days=62)


@Controller("v1/booking")
@UseGuards(RateLimitGuard)
class BookingController:
    def __init__(self, availability: AvailabilityService, bookings: BookingsService):
        self.availability = availability
        self.bookings = bookings

    @Get("availability")
    @RateLimit(120, 60)
    async def availability_slots(self, start: str = Query("from"), until: str = Query("to")) -> dict:
        try:
            lo, hi = parse_iso(start), parse_iso(until)
        except (ValueError, TypeError) as exc:
            raise BadRequestException("from and to must be ISO date-times.") from exc
        if hi <= lo or hi - lo > MAX_RANGE:
            raise BadRequestException("Choose a range of up to 62 days.")
        slots = await self.availability.slots(max(lo, now_utc() - timedelta(hours=1)), hi)
        return {"slots": [{"start": iso(s.start), "end": iso(s.end)} for s in slots]}

    @Post("holds")
    @RateLimit(10, 3600)
    async def create_hold(self, dto: HoldDto = Body()) -> dict:
        return await self.bookings.create_hold(dto)

    @Post("holds/:hold_id/resend")
    @RateLimit(10, 3600)
    async def resend(self, hold_id: str) -> dict:
        return await self.bookings.resend_code(hold_id)

    @Post("holds/:hold_id/verify")
    @RateLimit(30, 3600)
    async def verify(self, hold_id: str, dto: VerifyDto = Body()) -> dict:
        return await self.bookings.verify(hold_id, dto.code)

    @Get("manage/:token")
    @RateLimit(60, 60)
    async def view(self, token: str) -> dict:
        return await self.bookings.view(token)

    @Post("manage/:token/cancel")
    @RateLimit(20, 3600)
    async def cancel(self, token: str) -> dict:
        return await self.bookings.cancel(token)

    @Post("manage/:token/reschedule")
    @RateLimit(20, 3600)
    async def reschedule(self, token: str, dto: RescheduleDto = Body()) -> dict:
        return await self.bookings.reschedule(token, dto.start)
