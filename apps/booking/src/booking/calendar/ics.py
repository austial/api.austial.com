from __future__ import annotations

from datetime import datetime

from ..timeutil import now_utc


def _stamp(value: datetime) -> str:
    return value.strftime("%Y%m%dT%H%M%SZ")


def build_ics(uid: str, start: datetime, end: datetime, summary: str, meet_url: str | None, organizer: str) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Austial//Booking//EN",
        "METHOD:REQUEST",
        "BEGIN:VEVENT",
        f"UID:{uid}@austial.com",
        f"DTSTAMP:{_stamp(now_utc())}",
        f"DTSTART:{_stamp(start)}",
        f"DTEND:{_stamp(end)}",
        f"SUMMARY:{summary}",
        f"DESCRIPTION:{'Join: ' + meet_url if meet_url else 'Austial discovery call'}",
        f"LOCATION:{meet_url or 'Google Meet'}",
        f"ORGANIZER:mailto:{organizer}",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(lines) + "\r\n"
