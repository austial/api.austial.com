from __future__ import annotations

import logging
import secrets
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

import httpx
from austial import Injectable

from ..settings import Settings
from ..timeutil import iso, parse_iso

logger = logging.getLogger("booking.calendar")


@dataclass
class EventResult:
    event_id: str | None
    meet_url: str | None


@dataclass
class EventDetails:
    summary: str
    description: str
    start: datetime
    end: datetime
    timezone: str
    attendee_email: str


class CalendarProvider(ABC):
    """Injection token for the calendar. NullCalendar is used until Google is configured."""

    @abstractmethod
    async def busy(self, start: datetime, end: datetime) -> list[tuple[datetime, datetime]]: ...

    @abstractmethod
    async def create_event(self, details: EventDetails) -> EventResult: ...

    @abstractmethod
    async def move_event(self, event_id: str, details: EventDetails) -> None: ...

    @abstractmethod
    async def delete_event(self, event_id: str) -> None: ...


@Injectable()
class NullCalendar(CalendarProvider):
    """No calendar connected: no busy times, no events. Confirmation emails carry an .ics file instead."""

    async def busy(self, start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
        return []

    async def create_event(self, details: EventDetails) -> EventResult:
        return EventResult(None, None)

    async def move_event(self, event_id: str, details: EventDetails) -> None:
        return None

    async def delete_event(self, event_id: str) -> None:
        return None


@Injectable()
class GoogleCalendar(CalendarProvider):
    """Google Calendar through the REST API with a stored OAuth refresh token (your own account).

    Reads free/busy so booked or blocked times are not offered, creates the event with a Google Meet link, and
    lets Google email the invite to the visitor.
    """

    TOKEN_URL = "https://oauth2.googleapis.com/token"
    API = "https://www.googleapis.com/calendar/v3"

    def __init__(self, settings: Settings):
        self.s = settings
        self._token: str | None = None
        self._expires = 0.0

    async def _access_token(self, client: httpx.AsyncClient) -> str:
        if self._token and time.time() < self._expires - 60:
            return self._token
        res = await client.post(
            self.TOKEN_URL,
            data={
                "client_id": self.s.google_client_id,
                "client_secret": self.s.google_client_secret,
                "refresh_token": self.s.google_refresh_token,
                "grant_type": "refresh_token",
            },
        )
        res.raise_for_status()
        body = res.json()
        self._token = body["access_token"]
        self._expires = time.time() + int(body.get("expires_in", 3600))
        return self._token

    async def _call(self, method: str, path: str, **kwargs) -> httpx.Response:
        async with httpx.AsyncClient(timeout=15) as client:
            token = await self._access_token(client)
            res = await client.request(method, f"{self.API}{path}", headers={"Authorization": f"Bearer {token}"}, **kwargs)
            res.raise_for_status()
            return res

    @property
    def _cal(self) -> str:
        return self.s.google_calendar_id

    async def busy(self, start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
        res = await self._call(
            "POST", "/freeBusy", json={"timeMin": iso(start), "timeMax": iso(end), "items": [{"id": self._cal}]}
        )
        intervals = res.json().get("calendars", {}).get(self._cal, {}).get("busy", [])
        return [(parse_iso(i["start"]), parse_iso(i["end"])) for i in intervals]

    def _body(self, d: EventDetails) -> dict:
        return {
            "summary": d.summary,
            "description": d.description,
            "start": {"dateTime": iso(d.start), "timeZone": "UTC"},
            "end": {"dateTime": iso(d.end), "timeZone": "UTC"},
            "attendees": [{"email": d.attendee_email}],
        }

    async def create_event(self, details: EventDetails) -> EventResult:
        body = self._body(details)
        body["conferenceData"] = {
            "createRequest": {"requestId": secrets.token_hex(8), "conferenceSolutionKey": {"type": "hangoutsMeet"}}
        }
        res = await self._call(
            "POST", f"/calendars/{self._cal}/events", params={"conferenceDataVersion": 1, "sendUpdates": "all"}, json=body
        )
        data = res.json()
        return EventResult(data.get("id"), data.get("hangoutLink"))

    async def move_event(self, event_id: str, details: EventDetails) -> None:
        await self._call(
            "PATCH",
            f"/calendars/{self._cal}/events/{event_id}",
            params={"sendUpdates": "all"},
            json={"start": self._body(details)["start"], "end": self._body(details)["end"]},
        )

    async def delete_event(self, event_id: str) -> None:
        await self._call("DELETE", f"/calendars/{self._cal}/events/{event_id}", params={"sendUpdates": "all"})
