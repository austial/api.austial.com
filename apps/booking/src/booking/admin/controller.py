from __future__ import annotations

import hmac

from austial import Controller, Get, Injectable, NotFoundException, UnauthorizedException, UseGuards
from austial.common.guards.base import CanActivate, ExecutionContext
from austial.orm import FindOptions, InjectRepository, Repository
from austial.security import RateLimit, RateLimitGuard

from ..entities import Booking, Lead
from ..settings import Settings


@Injectable()
class AdminGuard(CanActivate):
    """Read-only admin access with one shared bearer token (ADMIN_TOKEN). With no token set the routes do not exist."""

    def __init__(self, settings: Settings):
        self.token = settings.admin_token

    async def can_activate(self, context: ExecutionContext) -> bool:
        if not self.token:
            raise NotFoundException("Not found")
        header = context.get_request().headers.get("authorization", "")
        scheme, _, supplied = header.partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(supplied.encode(), self.token.encode()):
            raise UnauthorizedException("Invalid admin token")
        return True


def _iso(value) -> str | None:
    return value.isoformat() + "Z" if value is not None else None


@Controller("v1/admin")
@UseGuards(RateLimitGuard, AdminGuard)
class AdminController:
    def __init__(
        self,
        leads: Repository[Lead] = InjectRepository(Lead),
        bookings: Repository[Booking] = InjectRepository(Booking),
    ):
        self.leads = leads
        self.bookings = bookings

    @Get("leads")
    @RateLimit(30, 60)
    async def list_leads(self) -> dict:
        rows = await self.leads.find(FindOptions(order_by=[("created_at", "DESC")]))
        return {
            "leads": [
                {
                    "id": r.id, "name": r.name, "email": r.email, "company": r.company, "website": r.website,
                    "services": r.services, "budget": r.budget, "timeline": r.timeline,
                    "description": r.description, "createdAt": _iso(r.created_at),
                }
                for r in rows[:500]
            ]
        }

    @Get("bookings")
    @RateLimit(30, 60)
    async def list_bookings(self) -> dict:
        rows = await self.bookings.find(FindOptions(order_by=[("start", "DESC")]))
        return {
            "bookings": [
                {
                    "id": r.id, "status": r.status, "start": _iso(r.start), "end": _iso(r.end), "timezone": r.timezone,
                    "name": r.name, "email": r.email, "company": r.company, "companyType": r.company_type,
                    "goal": r.goal, "meetUrl": r.meet_url, "createdAt": _iso(r.created_at),
                }
                for r in rows[:500]
            ]
        }
