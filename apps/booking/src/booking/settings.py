"""Typed settings read once from the environment through the framework's ConfigService."""

from __future__ import annotations

from austial import Injectable
from austial.config import ConfigService
from pydantic import BaseModel, Field


class EnvSchema(BaseModel):
    """Validated at startup by ConfigModule: a bad or missing value stops the app with a clear list."""

    APP_ENV: str = "dev"
    DATABASE_URL: str = "sqlite+aiosqlite:///./booking.db"
    DB_SYNCHRONIZE: bool = True
    SITE_URL: str = "https://services.austial.com"
    CORS_ORIGINS: str = "https://services.austial.com,http://localhost:3000,http://localhost:3101"
    CODE_PEPPER: str = Field(default="dev-only-change-me", min_length=8)
    TRUSTED_PROXY_HOPS: int = 0
    AVAILABILITY_FILE: str = "availability.toml"

    MAIL_BACKEND: str = "console"  # console | ses
    MAIL_FROM: str = "Austial <no-reply@austial.com>"
    MAIL_NOTIFY_TO: str = ""  # where new leads and bookings are sent to you; empty disables
    AWS_REGION: str = "us-east-1"

    CALENDAR_BACKEND: str = "none"  # none | google
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REFRESH_TOKEN: str = ""
    GOOGLE_CALENDAR_ID: str = "primary"

    HOLD_MINUTES: int = 15
    REMINDER_HOURS: int = 24


@Injectable()
class Settings:
    """Injectable, typed view of the environment."""

    def __init__(self, config: ConfigService):
        raw = {k: v for k, v in config.get_all().items() if k in EnvSchema.model_fields}
        s = EnvSchema.model_validate(raw)
        self.app_env = s.APP_ENV
        self.is_prod = s.APP_ENV == "prod"
        self.database_url = s.DATABASE_URL
        self.db_synchronize = s.DB_SYNCHRONIZE
        self.site_url = s.SITE_URL.rstrip("/")
        self.cors_origins = [o.strip() for o in s.CORS_ORIGINS.split(",") if o.strip()]
        self.code_pepper = s.CODE_PEPPER
        self.availability_file = s.AVAILABILITY_FILE
        self.mail_backend = s.MAIL_BACKEND
        self.mail_from = s.MAIL_FROM
        self.mail_notify_to = s.MAIL_NOTIFY_TO
        self.aws_region = s.AWS_REGION
        self.calendar_backend = s.CALENDAR_BACKEND
        self.google_client_id = s.GOOGLE_CLIENT_ID
        self.google_client_secret = s.GOOGLE_CLIENT_SECRET
        self.google_refresh_token = s.GOOGLE_REFRESH_TOKEN
        self.google_calendar_id = s.GOOGLE_CALENDAR_ID
        self.hold_minutes = s.HOLD_MINUTES
        self.reminder_hours = s.REMINDER_HOURS
        if self.is_prod and self.code_pepper == "dev-only-change-me":
            raise RuntimeError("CODE_PEPPER must be set in production.")
