from __future__ import annotations

import os

from austial import Module
from austial.config import ConfigModule, ConfigService
from austial.orm import OrmModule
from austial.security import SecurityConfig, SecurityModule

from .admin.controller import AdminController, AdminGuard
from .availability.service import AvailabilityService
from .bookings.controller import BookingController
from .bookings.service import BookingsService
from .calendar.provider import CalendarProvider, GoogleCalendar, NullCalendar
from .entities import ENTITIES
from .health.controller import HealthController
from .leads.controller import LeadsController
from .leads.service import LeadsService
from .mail.mailer import ConsoleMailer, Mailer, SesMailer
from .reminders.service import ReminderService
from .settings import EnvSchema, Settings


def _mailer(settings: Settings) -> Mailer:
    return SesMailer(settings) if settings.mail_backend == "ses" else ConsoleMailer(settings)


def _calendar(settings: Settings) -> CalendarProvider:
    return GoogleCalendar(settings) if settings.calendar_backend == "google" else NullCalendar()


def _synchronize() -> bool:
    """Create tables from the entities on start. Development convenience only: production uses migrations
    (python -m booking.migrate upgrade), so APP_ENV=prod turns this off unless DB_SYNCHRONIZE says otherwise."""
    default = "false" if os.getenv("APP_ENV") == "prod" else "true"
    return os.getenv("DB_SYNCHRONIZE", default).strip().lower() in {"1", "true", "yes"}


def _db(config: ConfigService) -> dict:
    url = config.get("DATABASE_URL") or EnvSchema.model_fields["DATABASE_URL"].default
    return {"type_": "postgres" if url.startswith("postgresql") else "sqlite", "url": url}


@Module(
    imports=[
        ConfigModule.for_root(".env", validation_schema=EnvSchema),
        OrmModule.for_root_async(use_factory=_db, inject=[ConfigService], entities=ENTITIES, synchronize=_synchronize()),
        OrmModule.for_feature(ENTITIES),
        SecurityModule.for_root(
            SecurityConfig(default_rate_limit=(120, 60), trusted_proxy_hops=int(os.getenv("TRUSTED_PROXY_HOPS", "0")))
        ),
    ],
    controllers=[BookingController, LeadsController, HealthController, AdminController],
    providers=[
        Settings,
        AdminGuard,
        {"provide": Mailer, "useFactory": _mailer, "inject": [Settings]},
        {"provide": CalendarProvider, "useFactory": _calendar, "inject": [Settings]},
        AvailabilityService,
        BookingsService,
        LeadsService,
        ReminderService,
    ],
)
class AppModule:
    pass
