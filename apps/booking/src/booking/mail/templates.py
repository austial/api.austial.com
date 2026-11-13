"""Email templates. Plain inline-styled HTML (email clients ignore stylesheets) matching the designed emails."""

from __future__ import annotations

from html import escape

from .mailer import Message

INK = "#161111"
BODY = "#4A4545"
DIM = "#6B6564"
EMBER = "#D63D17"
FONT = "Manrope, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "'Geist Mono', ui-monospace, Menlo, monospace"


def _button(label: str, href: str, dark: bool = True) -> str:
    bg, fg = (INK, "#FFFFFF") if dark else ("#F3EFEC", INK)
    return (
        f'<a href="{escape(href)}" style="display:inline-block;background:{bg};color:{fg};text-decoration:none;'
        f'font:700 14px/20px {FONT};padding:14px 22px;border-radius:20px;margin:0 8px 8px 0">{escape(label)}</a>'
    )


def _rows(rows: list[tuple[str, str]]) -> str:
    cells = "".join(
        f'<tr><td style="padding:14px 20px;border-bottom:1px solid rgba(22,17,17,.1);font:500 11px/1.6 {MONO};'
        f'letter-spacing:.08em;text-transform:uppercase;color:{DIM}">{escape(k)}</td>'
        f'<td style="padding:14px 20px;border-bottom:1px solid rgba(22,17,17,.1);font:700 15px/1.4 {FONT};color:{INK};'
        f'text-align:right">{escape(v)}</td></tr>'
        for k, v in rows
    )
    return f'<table role="presentation" width="100%" style="border:1px solid rgba(22,17,17,.1);border-radius:18px;background:#FAF8F6;border-collapse:separate">{cells}</table>'


def layout(eyebrow: str, heading: str, body_html: str, footer: str) -> str:
    return f"""<!doctype html><html><body style="margin:0;background:#EFEBE7;padding:32px 12px">
<div style="max-width:640px;margin:0 auto;font-family:{FONT};color:{BODY}">
<div style="background:#FFFFFF;border:1px solid rgba(22,17,17,.1);border-radius:24px;padding:40px">
<div style="font:700 16px/1 {FONT};color:{INK};margin-bottom:28px">Austial</div>
<div style="font:500 11px/1 {MONO};letter-spacing:.08em;text-transform:uppercase;color:{EMBER};margin-bottom:12px">( {escape(eyebrow)} )</div>
<h1 style="margin:0 0 16px;font:500 32px/1.1 {FONT};letter-spacing:-.02em;color:{INK}">{escape(heading)}</h1>
{body_html}
</div>
<div style="padding:20px 20px 0;font:400 12px/1.7 {FONT};color:{DIM}">{footer}</div>
</div></body></html>"""


def _p(text: str) -> str:
    return f'<p style="margin:0 0 20px;font:400 16px/1.7 {FONT}">{escape(text)}</p>'


FOOTER = "Austial, AI solutions for digital companies. You received this because of a request on services.austial.com."


def code_email(to: str, name: str, code: str, when: str, minutes: int) -> Message:
    spaced = f"{code[:3]} {code[3:]}"
    body = (
        _p(f"Hi {name}, enter this code on the booking page to hold your slot on {when}.")
        + f'<div style="border:1px solid rgba(22,17,17,.1);border-radius:18px;background:#FAF8F6;padding:28px;text-align:center;'
        f'font:500 44px/1 {MONO};letter-spacing:.3em;color:{INK};margin-bottom:20px">{spaced}</div>'
        + _p(f"The code expires in {minutes} minutes. If you did not request it, ignore this email and no booking will be made.")
    )
    text = f"Your Austial code: {spaced}\n\nUse it to hold your slot on {when}. It expires in {minutes} minutes.\nIf you did not request it, ignore this email."
    return Message(to, f"Your Austial code: {spaced}", text, layout("Confirm your booking", "Your verification code", body, FOOTER))


def confirmation_email(
    to: str, name: str, when: str, meet_url: str | None, manage_url: str, ics: str | None
) -> Message:
    where = "Google Meet" + (" (link below)" if meet_url else ", link to follow")
    buttons = (_button("Join Google Meet", meet_url) if meet_url else "") + _button("Reschedule or cancel", manage_url, dark=False)
    body = (
        _p(f"Thanks {name}. Your 30-minute discovery call is confirmed.")
        + _rows([("When", when), ("Where", where), ("Length", "30 minutes")])
        + '<div style="height:20px"></div>'
        + buttons
        + _p("Bring one metric you want to move and a rough idea of the data you have. We will take it from there.")
    )
    text = f"You are booked.\n\nWhen: {when}\nWhere: {where}\n" + (f"Join: {meet_url}\n" if meet_url else "") + f"\nReschedule or cancel: {manage_url}\n"
    return Message(to, f"You are booked: {when}", text, layout("Booking confirmed", f"You are booked, {name.split(' ')[0]}.", body, FOOTER), ics=ics)


def reminder_email(to: str, name: str, when: str, meet_url: str | None, manage_url: str) -> Message:
    buttons = (_button("Join Google Meet", meet_url) if meet_url else "") + _button("Reschedule or cancel", manage_url, dark=False)
    body = _p(f"Hi {name}, a quick reminder about your discovery call.") + _rows([("When", when)]) + '<div style="height:20px"></div>' + buttons
    text = f"Reminder: your call is {when}.\n" + (f"Join: {meet_url}\n" if meet_url else "") + f"Reschedule or cancel: {manage_url}\n"
    return Message(to, f"Reminder: your call is {when}", text, layout("Reminder", "Your call is coming up.", body, FOOTER))


def cancelled_email(to: str, name: str, when: str, site_url: str) -> Message:
    body = _p(f"Hi {name}, your call on {when} is cancelled and the slot is released.") + _button("Book a new time", f"{site_url}/book")
    return Message(to, "Your call is cancelled", f"Your call on {when} is cancelled.\nBook again: {site_url}/book\n", layout("Cancelled", "Your call is cancelled.", body, FOOTER))


def rescheduled_email(to: str, name: str, when: str, meet_url: str | None, manage_url: str, ics: str | None) -> Message:
    buttons = (_button("Join Google Meet", meet_url) if meet_url else "") + _button("Reschedule or cancel", manage_url, dark=False)
    body = _p(f"Hi {name}, your call has moved.") + _rows([("New time", when)]) + '<div style="height:20px"></div>' + buttons
    return Message(to, f"Your call has moved: {when}", f"Your call moved to {when}.\nManage: {manage_url}\n", layout("Rescheduled", "Your call has moved.", body, FOOTER), ics=ics)


def lead_ack_email(to: str, name: str, site_url: str) -> Message:
    body = _p(f"Hi {name}, thanks for your brief. We have it, and a person will read it and reply.") + _button("Book a call to move faster", f"{site_url}/book")
    return Message(to, "We have your brief", f"Hi {name}, we have your brief and will reply.\n", layout("Project brief", "We have your brief.", body, FOOTER))


def owner_lead_email(to: str, lead: dict[str, str]) -> Message:
    rows = [(k, v or "-") for k, v in lead.items()]
    body = _rows(rows)
    text = "New project brief\n\n" + "\n".join(f"{k}: {v}" for k, v in lead.items())
    return Message(to, f"New brief from {lead['name']} ({lead['company']})", text, layout("New lead", "New project brief", body, "Sent by the booking API."), reply_to=lead["email"])


def owner_booking_email(to: str, rows: list[tuple[str, str]], reply_to: str) -> Message:
    text = "New booking\n\n" + "\n".join(f"{k}: {v}" for k, v in rows)
    return Message(to, f"New booking: {dict(rows)['Name']}", text, layout("New booking", "New discovery call", _rows(rows), "Sent by the booking API."), reply_to=reply_to)
