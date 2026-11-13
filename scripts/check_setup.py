#!/usr/bin/env python3
"""Checks the SES and Google Calendar setup using the API's own backends.

    uv run python scripts/check_setup.py [path/to/env-file]      (default: docs/deploy/.env)

Sends one test email through Amazon SES to MAIL_NOTIFY_TO, asks Google for your free/busy times, and (with
--event) creates and deletes a throwaway Google Calendar event to prove the Meet link works.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "booking" / "src"))

from booking.calendar.provider import EventDetails, GoogleCalendar
from booking.mail.mailer import Message, SesMailer
from booking.timeutil import now_utc


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1].replace("'\\''", "'")
        values[key.strip()] = value
    return values


async def check_ses(env: dict[str, str]) -> bool:
    to = env.get("MAIL_NOTIFY_TO", "")
    if not to or not env.get("MAIL_FROM"):
        print("SES: skipped (MAIL_FROM and MAIL_NOTIFY_TO are needed)")
        return False
    import os

    os.environ["AWS_ACCESS_KEY_ID"] = env.get("AWS_ACCESS_KEY_ID", "")
    os.environ["AWS_SECRET_ACCESS_KEY"] = env.get("AWS_SECRET_ACCESS_KEY", "")
    mailer = SesMailer(
        SimpleNamespace(aws_region=env.get("AWS_REGION", "us-east-1"), mail_from=env["MAIL_FROM"])
    )  # type: ignore[arg-type]
    msg = Message(
        to=to,
        subject="Austial API: SES test",
        text="If you can read this, Amazon SES is set up and the booking API can send email.",
        html="<p>If you can read this, <b>Amazon SES</b> is set up and the booking API can send email.</p>",
    )
    try:
        await mailer.send(msg)
    except Exception as exc:  # noqa: BLE001
        print(f"SES: FAILED: {exc}")
        print("     In the sandbox you can only send to verified addresses, and MAIL_FROM must be verified.")
        return False
    print(f"SES: ok, test email sent to {to}")
    return True


async def check_google(env: dict[str, str], make_event: bool) -> bool:
    settings = SimpleNamespace(
        google_client_id=env.get("GOOGLE_CLIENT_ID", ""),
        google_client_secret=env.get("GOOGLE_CLIENT_SECRET", ""),
        google_refresh_token=env.get("GOOGLE_REFRESH_TOKEN", ""),
        google_calendar_id=env.get("GOOGLE_CALENDAR_ID", "primary"),
    )
    cal = GoogleCalendar(settings)  # type: ignore[arg-type]
    now = now_utc()
    try:
        busy = await cal.busy(now, now + timedelta(days=2))
    except Exception as exc:  # noqa: BLE001
        print(f"Google: FAILED reading free/busy: {exc}")
        return False
    print(f"Google: ok, free/busy works ({len(busy)} busy block(s) in the next 2 days)")
    if not make_event:
        return True
    start = now + timedelta(days=3)
    details = EventDetails(
        summary="Austial API test (safe to ignore)",
        description="Created by scripts/check_setup.py and deleted straight away.",
        start=start,
        end=start + timedelta(minutes=30),
        timezone="UTC",
        attendee_email=env.get("MAIL_NOTIFY_TO") or "",
    )
    try:
        result = await cal.create_event(details)
        print(f"Google: ok, test event created. Meet link: {result.meet_url or 'none returned'}")
        if result.event_id:
            await cal.delete_event(result.event_id)
            print("Google: test event deleted")
        return bool(result.meet_url)
    except Exception as exc:  # noqa: BLE001
        print(f"Google: FAILED creating the event: {exc}")
        return False


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("env_file", nargs="?", default=str(ROOT / "docs" / "deploy" / ".env"))
    parser.add_argument("--event", action="store_true", help="also create and delete a test calendar event")
    parser.add_argument("--only", choices=["ses", "google"])
    args = parser.parse_args()
    env = load_env(Path(args.env_file))
    results = []
    if args.only in (None, "ses"):
        results.append(await check_ses(env))
    if args.only in (None, "google"):
        results.append(await check_google(env, args.event))
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
