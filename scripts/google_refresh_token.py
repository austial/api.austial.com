#!/usr/bin/env python3
"""One-time helper: authorise your own Google account and print a refresh token for the booking API.

Reads GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET from the environment (so the secret never appears in a command
line). Opens your browser, receives Google's redirect on a local port, and prints ONLY the refresh token to stdout.
Everything else goes to stderr, so the wizard can capture the token cleanly.
"""

from __future__ import annotations

import os
import secrets
import sys
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import ClassVar

import httpx

SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.freebusy",
]
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"


def eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


class Receiver(BaseHTTPRequestHandler):
    result: ClassVar[dict[str, str]] = {}

    def do_GET(self) -> None:
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        Receiver.result = {k: v[0] for k, v in query.items()}
        ok = "code" in query
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        message = (
            "Authorised. You can close this tab and return to the terminal."
            if ok
            else "Authorisation failed. Return to the terminal."
        )
        self.wfile.write(
            f"<!doctype html><meta charset=utf-8><body style='font:18px system-ui;padding:48px'>{message}</body>".encode()
        )

    def log_message(self, *args: object) -> None:  # silence the access log
        return


def main() -> int:
    client_id = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        eprint("Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in the environment first.")
        return 2

    server = HTTPServer(("127.0.0.1", 0), Receiver)
    redirect = f"http://127.0.0.1:{server.server_port}"
    state = secrets.token_urlsafe(16)
    url = (
        AUTH_URL
        + "?"
        + urllib.parse.urlencode(
            {
                "client_id": client_id,
                "redirect_uri": redirect,
                "response_type": "code",
                "scope": " ".join(SCOPES),
                "access_type": "offline",
                "prompt": "consent",  # always returns a refresh token
                "state": state,
            }
        )
    )

    if os.environ.get("NO_BROWSER"):
        eprint("Open this URL in your browser:\n" + url)
    elif not webbrowser.open(url):
        eprint("Could not open a browser. Open this URL yourself:\n" + url)
    else:
        eprint("Your browser should be opening Google's consent page.")
    eprint(f"Waiting for Google to redirect to {redirect} ...")

    server.timeout = 300
    server.handle_request()
    server.server_close()

    got = Receiver.result
    if got.get("state") != state or "code" not in got:
        eprint(f"Authorisation did not complete: {got.get('error', 'no code received')}")
        return 1

    res = httpx.post(
        TOKEN_URL,
        data={
            "code": got["code"],
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect,
            "grant_type": "authorization_code",
        },
        timeout=20,
    )
    body = res.json()
    if res.status_code != 200 or "refresh_token" not in body:
        eprint(f"Token exchange failed: {body.get('error_description') or body}")
        return 1
    print(body["refresh_token"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
