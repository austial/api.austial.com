from __future__ import annotations

from austial import Controller, Get
from austial.orm import InjectRepository, Repository

from ..entities import Lead


@Controller("healthz")
class HealthController:
    def __init__(self, leads: Repository[Lead] = InjectRepository(Lead)):
        self.leads = leads

    @Get()
    async def check(self) -> dict:
        await self.leads.count()  # touches the database
        return {"ok": True}
