# Booking service. Build from the repository root: docker build -t api-booking .
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv

WORKDIR /app

# Dependencies first, so code changes do not reinstall them.
COPY pyproject.toml uv.lock ./
COPY apps/booking/pyproject.toml apps/booking/pyproject.toml
RUN uv sync --frozen --no-dev --package booking --no-install-workspace

COPY apps/booking apps/booking

RUN useradd --create-home --uid 10001 app && chown -R app /app
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)" || exit 1

# Migrations run first, then the server. --proxy-headers: Caddy terminates TLS in front, so trust one hop
# (also set TRUSTED_PROXY_HOPS=1).
ENV PYTHONPATH=/app/apps/booking/src
CMD ["sh", "-c", "uv run --no-dev --package booking python -m booking.migrate upgrade && exec uv run --no-dev --package booking uvicorn booking.main:app --app-dir apps/booking/src --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips '*'"]
