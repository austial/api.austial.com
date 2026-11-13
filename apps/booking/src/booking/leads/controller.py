from __future__ import annotations

from austial import Body, Controller, Post, UseGuards
from austial.security import RateLimit, RateLimitGuard

from .service import BriefDto, LeadsService


@Controller("v1/leads")
@UseGuards(RateLimitGuard)
class LeadsController:
    def __init__(self, leads: LeadsService):
        self.leads = leads

    @Post()
    @RateLimit(5, 3600)
    async def create(self, dto: BriefDto = Body()) -> dict:
        return await self.leads.create(dto)
