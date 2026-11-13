from __future__ import annotations

import logging

from austial import AllExceptionsFilter, AustialFactory
from austial.common.pipes import ValidationPipe

from .app_module import AppModule
from .settings import Settings


def _configure_logging() -> None:
    """Show the app's own logs (including dev emails) next to the server output."""
    log = logging.getLogger("booking")
    if not log.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s [%(name)s] %(message)s"))
        log.addHandler(handler)
    log.setLevel(logging.INFO)
    log.propagate = False


def build():
    _configure_logging()
    app = AustialFactory.create(AppModule, title="Austial services API")
    app.use_global_pipes(ValidationPipe())
    app.use_global_filters(AllExceptionsFilter())
    settings = app.get(Settings)
    app.enable_cors(
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Accept"],
        max_age=600,
    )
    return app


app = build()
