# api.austial.com

Backend for [services.austial.com](https://services.austial.com), built on the [Austial framework](https://docs.austial.com) (a NestJS-style framework for Python on FastAPI). It is a monorepo: each service is an app under `apps/`. Today there is one, `booking`.

## What `apps/booking` does

- **Availability** from weekly hours in `availability.toml`, minus existing bookings, live holds and (when connected) your Google Calendar busy times.
- **Holds with email codes.** A visitor picks a slot, the slot is held for 15 minutes and a 6-digit code is emailed. Codes are stored as an HMAC, limited to 5 attempts, and can be resent (with a cooldown).
- **Bookings.** Entering the code confirms the booking, creates a Google Calendar event with a Meet link, and sends a confirmation (plus a copy to you).
- **Reschedule and cancel** through a private link in the email.
- **Reminders** 24 hours before a call, from an in-process loop (no separate worker). State is in the database, so a restart never repeats or loses a reminder.
- **Project briefs** (`/v1/leads`) with a honeypot, rate limits, a confirmation to the sender and a notification to you.

Framework pieces used: `Module`, `Controller`, `Injectable` providers with constructor injection, `ConfigModule` with a validated schema, `austial.orm` (entities and repositories, Postgres via asyncpg, SQLite for dev), `SecurityModule` rate limiting, `ValidationPipe`, `AllExceptionsFilter`, lifecycle hooks and `austial.testing`.

## Run it

```bash
uv sync --all-packages
cp apps/booking/.env.example apps/booking/.env   # dev defaults: SQLite, emails printed to the log, no calendar
cd apps/booking && uv run uvicorn booking.main:app --app-dir src --reload --port 4010
```

In dev, `MAIL_BACKEND=console` prints every email (including the 6-digit code) to the server log. Point the site at it with `NEXT_PUBLIC_API_URL=http://localhost:4010`.

```bash
uv run pytest -q     # 15 tests: availability, holds, codes, booking, reschedule, cancel, reminders, leads, rate limits
uv run ruff check .
```

## Configuration

| Variable | Purpose |
|---|---|
| `APP_ENV` | `dev`, `prod` or `test`. In `prod` a real `CODE_PEPPER` is required. |
| `DATABASE_URL` | `postgresql+asyncpg://...` (production) or `sqlite+aiosqlite:///./booking.db` (dev). |
| `SITE_URL`, `CORS_ORIGINS` | Used for links in emails and the browser origins allowed to call the API. |
| `CODE_PEPPER` | Secret for hashing codes and deriving manage links. Rotating it invalidates both. |
| `TRUSTED_PROXY_HOPS` | `1` behind Caddy, so client IPs for rate limiting are right. |
| `MAIL_BACKEND` | `console` or `ses`. `MAIL_FROM` must be a verified SES identity. `MAIL_NOTIFY_TO` receives new bookings and briefs. |
| `CALENDAR_BACKEND` | `none` or `google`. See below. |

Edit `apps/booking/availability.toml` for your real hours, time zone, buffer and notice. The defaults (Asia/Kolkata, Monday to Friday 10:00 to 17:00) are placeholders for you to confirm.

## One-time setup

**Guided setup.** `scripts/setup-services.sh` walks you through everything below (SES, Google, database), writes `docs/deploy/.env`, and can send a test email and read your calendar. Re-run it any time; it keeps values already saved. `uv run python scripts/check_setup.py --event` re-runs just the checks.

**Amazon SES.** Verify your sending domain, request production access (new accounts start in the sandbox), and give the API an IAM user or role that can `ses:SendRawEmail` or `sesv2:SendEmail`.

**Google Calendar and Meet.** In Google Cloud, create an OAuth client, enable the Calendar API, and authorise your own account once with the scopes `calendar.events` and `calendar.freebusy` (the wizard does this for you). Put the client id, secret and the resulting **refresh token** in the env file. The API then reads free/busy, creates events with a Meet link and lets Google email the invite.

## Deploy (DigitalOcean Droplet)

`docs/deploy/docker-compose.yml` runs Caddy (automatic HTTPS for `api.austial.com`) and the API container. The database is Managed Postgres. `.github/workflows/deploy.yml` tests, builds an image to GHCR and deploys over SSH when you push to `main`. Repository secrets: `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, `GHCR_PULL_TOKEN`. Put `docs/deploy/` on the server at `/opt/api` with a filled-in `.env`.

## Known limits (v0.1)

- Schema changes go through versioned migrations: `python -m booking.migrate revision "message"` (review the file), then the container applies them on start. Dev and tests still create tables from the entities.
- Rate limits and the booking lock live in memory, which is right for one container. Add a shared store before running several.
- CI builds the Dockerfile and pushes the image. The SSH deploy step has not yet run against a real Droplet.
- The Google Calendar and SES backends are implemented but not exercised against the real services.
