from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from email.message import EmailMessage

from austial import Injectable

from ..settings import Settings

logger = logging.getLogger("booking.mail")


@dataclass
class Message:
    to: str
    subject: str
    text: str
    html: str
    ics: str | None = None
    reply_to: str | None = None


class Mailer(ABC):
    """Injection token for sending email. The concrete class is chosen by MAIL_BACKEND."""

    @abstractmethod
    async def send(self, message: Message) -> None: ...


def build_mime(sender: str, message: Message) -> EmailMessage:
    mime = EmailMessage()
    mime["From"] = sender
    mime["To"] = message.to
    mime["Subject"] = message.subject
    if message.reply_to:
        mime["Reply-To"] = message.reply_to
    mime.set_content(message.text)
    mime.add_alternative(message.html, subtype="html")
    if message.ics:
        mime.add_attachment(
            message.ics.encode("utf-8"),
            maintype="text",
            subtype="calendar",
            filename="austial-call.ics",
            params={"method": "REQUEST"},
        )
    return mime


@Injectable()
class ConsoleMailer(Mailer):
    """Development backend: prints the email instead of sending it."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.sent: list[Message] = []

    async def send(self, message: Message) -> None:
        self.sent.append(message)
        logger.info("EMAIL to=%s subject=%s\n%s", message.to, message.subject, message.text)


@Injectable()
class SesMailer(Mailer):
    """Sends through Amazon SES (raw MIME, so attachments work). Credentials come from the standard AWS env vars or role."""

    def __init__(self, settings: Settings):
        import boto3

        self.settings = settings
        self.client = boto3.client("sesv2", region_name=settings.aws_region)

    async def send(self, message: Message) -> None:
        mime = build_mime(self.settings.mail_from, message)

        def _send() -> None:
            self.client.send_email(
                FromEmailAddress=self.settings.mail_from,
                Destination={"ToAddresses": [message.to]},
                Content={"Raw": {"Data": mime.as_bytes()}},
            )

        await asyncio.to_thread(_send)
