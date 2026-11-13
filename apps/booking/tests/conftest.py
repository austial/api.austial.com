from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

_db = Path(tempfile.mkdtemp()) / "test.db"
os.environ.update(
    {
        "APP_ENV": "test",
        "DATABASE_URL": f"sqlite+aiosqlite:///{_db}",
        "CODE_PEPPER": "test-pepper-123",
        "MAIL_BACKEND": "console",
        "CALENDAR_BACKEND": "none",
        "MAIL_NOTIFY_TO": "owner@example.com",
        "ADMIN_TOKEN": "test-admin-token",
        "SITE_URL": "https://services.example.test",
        "AVAILABILITY_FILE": str(Path(__file__).parent / "availability.test.toml"),
    }
)


@pytest.fixture
async def app(tmp_path):
    # A fresh database per test keeps the tests independent of each other.
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    from booking.main import build

    application = build()
    await application.init()
    yield application


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
        yield c


@pytest.fixture
def mailer(app):
    from booking.mail.mailer import Mailer

    m = app.get(Mailer)
    m.sent.clear()
    return m
