from __future__ import annotations

from datetime import datetime

from austial.orm import Column, Entity, PrimaryColumn, Text


@Entity("holds")
class Hold:
    """A slot held for a visitor until they enter the emailed code."""

    id: str = PrimaryColumn()
    start: datetime = Column(index=True)
    end: datetime = Column()
    timezone: str = Column()
    name: str = Column()
    email: str = Column(index=True)
    company: str = Column()
    company_type: str = Column()
    goal: str = Column(type_=Text)
    code_hash: str = Column()
    attempts: int = Column(default=0)
    sends: int = Column(default=1)
    last_sent_at: datetime = Column()
    expires_at: datetime = Column(index=True)
    status: str = Column(default="pending", index=True)  # pending | confirmed | expired
    created_at: datetime = Column()


@Entity("bookings")
class Booking:
    id: str = PrimaryColumn()
    hold_id: str = Column()
    start: datetime = Column(index=True)
    end: datetime = Column()
    timezone: str = Column()
    name: str = Column()
    email: str = Column()
    company: str = Column()
    company_type: str = Column()
    goal: str = Column(type_=Text)
    token_hash: str = Column(unique=True)
    status: str = Column(default="confirmed", index=True)  # confirmed | cancelled
    event_id: str = Column(nullable=True)
    meet_url: str = Column(nullable=True)
    reminder_sent_at: datetime = Column(nullable=True)
    created_at: datetime = Column()


@Entity("leads")
class Lead:
    id: str = PrimaryColumn()
    name: str = Column()
    email: str = Column()
    company: str = Column()
    website: str = Column(nullable=True)
    services: str = Column(type_=Text, default="")
    budget: str = Column(nullable=True)
    timeline: str = Column(nullable=True)
    description: str = Column(type_=Text)
    created_at: datetime = Column()


ENTITIES = [Hold, Booking, Lead]
