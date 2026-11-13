# api.austial.com

Backend services for services.austial.com on the Austial framework (`austial` 0.6.x). One app per service under `apps/`; today only `apps/booking`. Use the terms in `GLOSSARY.md`; read `docs/adr` before reversing a decision.

Check changes with `uv run ruff check . && uv run pytest -q` (tests use `austial.testing` and the console mailer, no network). Follow the framework's module shape: Module, Controller, Injectable, and `Repository` from `OrmModule`. `uv sync --all-packages` installs every app.

The end-to-end launch plan is in the services site repo, `docs/plan.md`; deploy and environment setup is `README.md`, `scripts/setup-services.sh` (SES, Google, database) and `scripts/setup-deploy.sh` (server, pipeline, Vercel, live checks).

Never commit `.env` files or real credentials; the setup wizard writes `docs/deploy/.env`, which is git-ignored.
