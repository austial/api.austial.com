from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime, timedelta

from austial import Injectable, OnApplicationBootstrap, OnApplicationShutdown
from austial.orm import FindOptions, InjectRepository, IsNull, Repository

from ..bookings.service import BookingsService, format_when
from ..entities import Booking, Hold
from ..mail import templates
from ..mail.mailer import Mailer
from ..settings import Settings
from ..timeutil import as_utc, now_utc, to_db

logger = logging.getLogger("booking.reminders")
INTERVAL_SECONDS = 60


@Injectable()
class ReminderService(OnApplicationBootstrap, OnApplicationShutdown):
    """In-process scheduler: no separate worker. Sends one reminder per booking and expires stale holds.

    A plain loop on the framework's lifecycle hooks. The state lives in the database (reminder_sent_at) and each
    reminder is claimed with a conditional update, so neither a restart nor a second container repeats one.
    """

    def __init__(
        self,
        settings: Settings,
        mailer: Mailer,
        bookings_service: BookingsService,
        bookings: Repository[Booking] = InjectRepository(Booking),
        holds: Repository[Hold] = InjectRepository(Hold),
    ):
        self.s = settings
        self.mailer = mailer
        self.service = bookings_service
        self.bookings = bookings
        self.holds = holds
        self._task: asyncio.Task | None = None

    async def on_application_bootstrap(self) -> None:
        if self.s.app_env == "test":
            return
        self._task = asyncio.create_task(self._loop(), name="booking-reminders")

    async def on_application_shutdown(self, signal: str | None = None) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _loop(self) -> None:
        while True:
            try:
                await self.run_once()
            except Exception as exc:  # noqa: BLE001 - keep the loop alive
                logger.error("reminder pass failed: %r", exc)
            await asyncio.sleep(INTERVAL_SECONDS)

    async def run_once(self, now: datetime | None = None) -> int:
        now = now or now_utc()
        horizon = now + timedelta(hours=self.s.reminder_hours)
        sent = 0
        for b in await self.bookings.find(FindOptions(where={"status": "confirmed"})):
            if b.reminder_sent_at is not None:
                continue
            start = as_utc(b.start)
            if not (now < start <= horizon):
                continue
            # Claim the booking in the database before sending: only one container can win this update, so
            # several containers never send the same reminder. Give the claim back if the send fails.
            claimed = await self.bookings.update({"id": b.id, "reminder_sent_at": IsNull()}, {"reminder_sent_at": to_db(now)})
            if claimed.affected != 1:
                continue
            try:
                await self.mailer.send(
                    templates.reminder_email(
                        b.email, b.name, format_when(start, b.timezone), b.meet_url, self.service.manage_url(b)
                    )
                )
            except Exception as exc:  # noqa: BLE001 - try again next pass
                logger.error("reminder for %s failed: %r", b.id, exc)
                await self.bookings.update({"id": b.id}, {"reminder_sent_at": None})
                continue
            sent += 1
        for h in await self.holds.find(FindOptions(where={"status": "pending"})):
            if as_utc(h.expires_at) <= now:
                await self.holds.update({"id": h.id}, {"status": "expired"})
        return sent
