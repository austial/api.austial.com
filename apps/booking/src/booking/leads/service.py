from __future__ import annotations

import logging
import re
import secrets

from austial import Injectable
from austial.orm import InjectRepository, Repository
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..entities import Lead
from ..mail import templates
from ..mail.mailer import Mailer, Message
from ..settings import Settings
from ..timeutil import now_utc, to_db

logger = logging.getLogger("booking.leads")
EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class BriefDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(min_length=2, max_length=120)
    email: str = Field(max_length=200)
    company: str = Field(min_length=2, max_length=120)
    website: str = Field(default="", max_length=300)
    services: list[str] = Field(default_factory=list, max_length=8)
    budget: str = Field(default="", max_length=60)
    timeline: str = Field(default="", max_length=60)
    description: str = Field(min_length=20, max_length=6000)
    hp: str = Field(default="", max_length=500)  # honeypot

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if not EMAIL.match(v):
            raise ValueError("Enter a valid email address.")
        return v


@Injectable()
class LeadsService:
    def __init__(self, settings: Settings, mailer: Mailer, leads: Repository[Lead] = InjectRepository(Lead)):
        self.s = settings
        self.mailer = mailer
        self.leads = leads

    async def _safe_send(self, message: Message) -> None:
        try:
            await self.mailer.send(message)
        except Exception as exc:  # noqa: BLE001
            logger.error("email to %s failed: %r", message.to, exc)

    async def create(self, dto: BriefDto) -> dict:
        if dto.hp.strip():
            # A bot filled the hidden field: answer as if it worked, store nothing.
            logger.info("honeypot hit, brief dropped")
            return {"id": "ok"}
        lead = Lead(
            id=secrets.token_urlsafe(10),
            name=" ".join(dto.name.split()),
            email=dto.email,
            company=" ".join(dto.company.split()),
            website=dto.website.strip() or None,
            services=", ".join(dto.services),
            budget=dto.budget or None,
            timeline=dto.timeline or None,
            description=dto.description.strip(),
            created_at=to_db(now_utc()),
        )
        await self.leads.insert(lead)
        await self._safe_send(templates.lead_ack_email(lead.email, lead.name.split(" ")[0], self.s.site_url))
        if self.s.mail_notify_to:
            await self._safe_send(
                templates.owner_lead_email(
                    self.s.mail_notify_to,
                    {
                        "name": lead.name,
                        "email": lead.email,
                        "company": lead.company,
                        "website": lead.website or "",
                        "services": lead.services,
                        "budget": lead.budget or "",
                        "timeline": lead.timeline or "",
                        "description": lead.description,
                    },
                )
            )
        return {"id": lead.id}
