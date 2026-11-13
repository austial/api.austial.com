from __future__ import annotations

import pytest


def brief(**over):
    body = {
        "name": "Brief Person",
        "email": "brief@example.com",
        "company": "Brief Co",
        "website": "brief.example",
        "services": ["Agents and automation"],
        "budget": "$1k to $5k",
        "timeline": "This quarter",
        "description": "We want to automate tier-one support with an agent.",
        "hp": "",
    }
    body.update(over)
    return body


async def test_health(client):
    res = await client.get("/healthz")
    assert res.status_code == 200 and res.json() == {"ok": True}


async def test_brief_is_stored_and_emails_go_out(client, mailer):
    res = await client.post("/v1/leads", json=brief())
    assert res.status_code in (200, 201), res.text
    assert res.json()["id"] not in ("", "ok")
    subjects = [m.subject for m in mailer.sent]
    assert "We have your brief" in subjects
    assert any(s.startswith("New brief from Brief Person") for s in subjects)


async def test_honeypot_is_accepted_but_dropped(client, mailer):
    res = await client.post("/v1/leads", json=brief(hp="http://spam.example"))
    assert res.status_code in (200, 201) and res.json() == {"id": "ok"}
    assert mailer.sent == []


@pytest.mark.parametrize("field,value", [("email", "nope"), ("description", "too short"), ("name", "x")])
async def test_brief_validation(client, field, value):
    res = await client.post("/v1/leads", json=brief(**{field: value}))
    assert res.status_code == 400


async def test_brief_is_rate_limited(client):
    codes = []
    for i in range(7):
        codes.append((await client.post("/v1/leads", json=brief(email=f"rl{i}@example.com"))).status_code)
    assert 429 in codes
