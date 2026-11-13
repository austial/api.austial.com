from __future__ import annotations

import re
from datetime import timedelta

from booking.timeutil import iso, now_utc


def window():
    start = now_utc() + timedelta(days=2)
    return iso(start), iso(start + timedelta(days=3))


async def first_slots(client, n=3):
    lo, hi = window()
    res = await client.get("/v1/booking/availability", params={"from": lo, "to": hi})
    assert res.status_code == 200, res.text
    slots = res.json()["slots"]
    assert len(slots) >= n
    return slots


def hold_body(start: str, email="visitor@example.com"):
    return {
        "start": start,
        "timezone": "Europe/Berlin",
        "name": "Test Visitor",
        "email": email,
        "company": "Test Co",
        "companyType": "SaaS",
        "goal": "Reduce support response time with an agent.",
    }


def code_from(mailer) -> str:
    msg = next(m for m in reversed(mailer.sent) if "code" in m.subject.lower())
    return re.search(r"(\d{3}) (\d{3})", msg.subject).group(1) + re.search(r"(\d{3}) (\d{3})", msg.subject).group(2)


async def test_availability_lists_configured_slots(client):
    slots = await first_slots(client)
    assert all(s["start"].endswith("Z") for s in slots)
    starts = {s["start"][11:16] for s in slots}
    assert starts <= {"09:00", "09:30", "10:00", "10:30"}


async def test_availability_rejects_bad_ranges(client):
    res = await client.get("/v1/booking/availability", params={"from": "nonsense", "to": "x"})
    assert res.status_code == 400
    lo = iso(now_utc())
    res = await client.get("/v1/booking/availability", params={"from": lo, "to": iso(now_utc() + timedelta(days=200))})
    assert res.status_code == 400


async def test_full_booking_flow_and_slot_is_removed(client, mailer):
    slots = await first_slots(client)
    start = slots[0]["start"]

    res = await client.post("/v1/booking/holds", json=hold_body(start))
    assert res.status_code in (200, 201), res.text
    hold = res.json()
    assert hold["holdId"] and hold["expiresAt"].endswith("Z")
    code = code_from(mailer)

    # the held slot is no longer offered to anyone else
    again = await first_slots(client, 1)
    assert start not in [s["start"] for s in again]

    bad = await client.post(f"/v1/booking/holds/{hold['holdId']}/verify", json={"code": "000000" if code != "000000" else "111111"})
    assert bad.status_code == 400

    ok = await client.post(f"/v1/booking/holds/{hold['holdId']}/verify", json={"code": code})
    assert ok.status_code in (200, 201), ok.text
    booking = ok.json()["booking"]
    assert booking["start"] == start and booking["end"] > start

    subjects = [m.subject for m in mailer.sent]
    assert any(s.startswith("You are booked") for s in subjects)
    assert any(s.startswith("New booking") for s in subjects)  # owner notification
    confirmation = next(m for m in mailer.sent if m.subject.startswith("You are booked"))
    assert confirmation.ics and "BEGIN:VEVENT" in confirmation.ics  # no calendar connected: ics fallback
    assert "https://services.example.test/manage/" in confirmation.text

    # the booked slot stays unavailable
    after = await first_slots(client, 1)
    assert start not in [s["start"] for s in after]


async def test_same_slot_cannot_be_held_twice(client, mailer):
    start = (await first_slots(client))[1]["start"]
    first = await client.post("/v1/booking/holds", json=hold_body(start, "a@example.com"))
    assert first.status_code in (200, 201)
    second = await client.post("/v1/booking/holds", json=hold_body(start, "b@example.com"))
    assert second.status_code == 409


async def test_wrong_codes_lock_the_hold(client, mailer):
    start = (await first_slots(client))[2]["start"]
    hold = (await client.post("/v1/booking/holds", json=hold_body(start, "lock@example.com"))).json()
    real = code_from(mailer)
    wrong = "123456" if real != "123456" else "654321"
    for _ in range(5):
        assert (await client.post(f"/v1/booking/holds/{hold['holdId']}/verify", json={"code": wrong})).status_code == 400
    locked = await client.post(f"/v1/booking/holds/{hold['holdId']}/verify", json={"code": real})
    assert locked.status_code == 429


async def test_validation_errors(client):
    start = (await first_slots(client))[0]["start"]
    bad = hold_body(start)
    bad["email"] = "not-an-email"
    assert (await client.post("/v1/booking/holds", json=bad)).status_code == 400
    bad = hold_body(start)
    bad["goal"] = "short"
    assert (await client.post("/v1/booking/holds", json=bad)).status_code == 400
    assert (await client.post("/v1/booking/holds/nope/verify", json={"code": "12ab56"})).status_code == 400
    assert (await client.post("/v1/booking/holds/nope/verify", json={"code": "123456"})).status_code == 404


async def test_manage_cancel_and_reschedule(client, mailer, app):
    slots = await first_slots(client, 5)
    start, other = slots[3]["start"], slots[4]["start"]
    hold = (await client.post("/v1/booking/holds", json=hold_body(start, "manage@example.com"))).json()
    booking = (await client.post(f"/v1/booking/holds/{hold['holdId']}/verify", json={"code": code_from(mailer)})).json()["booking"]
    confirmation = next(m for m in mailer.sent if m.subject.startswith("You are booked"))
    token = re.search(r"/manage/([\w-]+)", confirmation.text).group(1)

    view = await client.get(f"/v1/booking/manage/{token}")
    assert view.status_code == 200 and view.json()["id"] == booking["id"]
    assert (await client.get("/v1/booking/manage/not-a-token")).status_code == 404

    moved = await client.post(f"/v1/booking/manage/{token}/reschedule", json={"start": other})
    assert moved.status_code in (200, 201), moved.text
    assert moved.json()["start"] == other
    # the old time is free again, the new one is taken
    now_slots = [s["start"] for s in await first_slots(client, 1)]
    assert start in now_slots and other not in now_slots

    cancelled = await client.post(f"/v1/booking/manage/{token}/cancel")
    assert cancelled.json()["status"] == "cancelled"
    assert other in [s["start"] for s in await first_slots(client, 1)]
    assert any(m.subject == "Your call is cancelled" for m in mailer.sent)


async def test_reminder_is_sent_once(app, mailer, client):
    from booking.reminders.service import ReminderService

    slots = await first_slots(client, 6)
    start = slots[5]["start"]
    hold = (await client.post("/v1/booking/holds", json=hold_body(start, "remind@example.com"))).json()
    await client.post(f"/v1/booking/holds/{hold['holdId']}/verify", json={"code": code_from(mailer)})
    svc = app.get(ReminderService)
    soon = now_utc() + timedelta(days=100)  # not yet due
    assert await svc.run_once(now_utc()) == 0
    due = (await first_slots(client, 1)) and now_utc()
    # move "now" to just inside the reminder window of that booking
    from booking.timeutil import parse_iso

    inside = parse_iso(start) - timedelta(hours=2)
    assert await svc.run_once(inside) >= 1
    assert any(m.subject.startswith("Reminder") for m in mailer.sent)
    assert await svc.run_once(inside) == 0  # only once
    assert soon > due


async def _booked_slot(client, mailer, email):
    start = (await first_slots(client, 6))[5]["start"]
    hold = (await client.post("/v1/booking/holds", json=hold_body(start, email))).json()
    await client.post(f"/v1/booking/holds/{hold['holdId']}/verify", json={"code": code_from(mailer)})
    return start


async def test_two_reminder_passes_at_once_send_one_reminder(app, mailer, client):
    import asyncio

    from booking.reminders.service import ReminderService
    from booking.timeutil import parse_iso

    start = await _booked_slot(client, mailer, "race@example.com")
    svc = app.get(ReminderService)
    inside = parse_iso(start) - timedelta(hours=2)
    results = await asyncio.gather(svc.run_once(inside), svc.run_once(inside))
    assert sum(results) == 1
    assert len([m for m in mailer.sent if m.subject.startswith("Reminder")]) == 1


async def test_failed_reminder_is_retried_on_the_next_pass(app, mailer, client):
    from booking.reminders.service import ReminderService
    from booking.timeutil import parse_iso

    start = await _booked_slot(client, mailer, "retry@example.com")
    svc = app.get(ReminderService)
    inside = parse_iso(start) - timedelta(hours=2)
    real_send = svc.mailer.send

    async def boom(message):
        raise RuntimeError("ses is down")

    svc.mailer.send = boom
    assert await svc.run_once(inside) == 0
    svc.mailer.send = real_send
    assert await svc.run_once(inside) == 1
