from types import SimpleNamespace

import pytest
from austial import NotFoundException

from booking.admin.controller import AdminGuard

AUTH = {"authorization": "Bearer test-admin-token"}
LEAD = {
    "name": "Ada Lovelace", "email": "ada@example.com", "company": "Analytical Co",
    "services": ["AI agents and workflow automation"], "description": "We want to automate our support queue properly.",
    "hp": "",
}


async def test_admin_requires_the_token(client):
    assert (await client.get("/v1/admin/leads")).status_code == 401
    assert (await client.get("/v1/admin/leads", headers={"authorization": "Bearer wrong"})).status_code == 401
    assert (await client.get("/v1/admin/bookings", headers={"authorization": "Basic test-admin-token"})).status_code == 401


async def test_admin_lists_leads_and_bookings(client):
    await client.post("/v1/leads", json=LEAD)
    res = await client.get("/v1/admin/leads", headers=AUTH)
    assert res.status_code == 200, res.text
    leads = res.json()["leads"]
    assert [x["email"] for x in leads] == ["ada@example.com"]
    assert (await client.get("/v1/admin/bookings", headers=AUTH)).json() == {"bookings": []}


async def test_admin_does_not_exist_without_a_token():
    guard = AdminGuard(SimpleNamespace(admin_token=""))
    with pytest.raises(NotFoundException):
        await guard.can_activate(SimpleNamespace(get_request=lambda: SimpleNamespace(headers={})))
