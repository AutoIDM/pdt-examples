#!/usr/bin/env python3
"""Local stand-ins for Entra ID and, optionally, the Monday GraphQL API.

Entra serves the client-credentials token route and Graph /users.
Monday serves the users query the report sends. No real credentials.

dvisch@autoidm.com is present and disabled, so a live Monday tenant whose
only active user is that address shows up as orphaned. The Monday fixture
also includes Contoso accounts so the all-mock run finds several orphans.
"""

from __future__ import annotations

import argparse
import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

GRAPH_TOKEN = "demo-graph-token"

ENTRA_USERS = [
    {
        "id": "entra-ada",
        "displayName": "Ada Lovelace",
        "userPrincipalName": "ada.lovelace@contoso.com",
        "accountEnabled": True,
    },
    {
        "id": "entra-alan",
        "displayName": "Alan Turing",
        "userPrincipalName": "alan.turing@contoso.com",
        "accountEnabled": True,
    },
    {
        "id": "entra-grace",
        "displayName": "Grace Hopper",
        "userPrincipalName": "grace.hopper@contoso.com",
        "accountEnabled": False,
    },
    {
        "id": "entra-katherine",
        "displayName": "Katherine Johnson",
        "userPrincipalName": "kjohnson@contoso.com",
        "accountEnabled": True,
    },
    {
        "id": "entra-tim",
        "displayName": "Tim Berners-Lee",
        "userPrincipalName": "tim.berners-lee@contoso.com",
        "accountEnabled": True,
    },
    {
        "id": "entra-derek",
        "displayName": "Derek Visch",
        "userPrincipalName": "dvisch@autoidm.com",
        "accountEnabled": False,
    },
]

MONDAY_USERS = [
    {
        "id": "1001",
        "name": "Ada Lovelace",
        "email": "Ada.Lovelace@Contoso.com",
        "status": "ACTIVE",
        "url": "https://contoso.monday.com/users/1001",
    },
    {
        "id": "1002",
        "name": "Alan Turing",
        "email": "alan.turing@contoso.com",
        "status": "ACTIVE",
        "url": "https://contoso.monday.com/users/1002",
    },
    {
        "id": "1003",
        "name": "Grace Hopper",
        "email": "grace.hopper@contoso.com",
        "status": "ACTIVE",
        "url": "https://contoso.monday.com/users/1003",
    },
    {
        "id": "1004",
        "name": "Linus Torvalds",
        "email": "linus.torvalds@contoso.com",
        "status": "ACTIVE",
        "url": "https://contoso.monday.com/users/1004",
    },
    {
        "id": "1005",
        "name": "Katherine Johnson",
        "email": "katherine.johnson@contoso.com",
        "status": "ACTIVE",
        "url": "https://contoso.monday.com/users/1005",
    },
    {
        "id": "1006",
        "name": "Margaret Hamilton",
        "email": "margaret.hamilton@contoso.com",
        "status": "INACTIVE",
        "url": "https://contoso.monday.com/users/1006",
    },
]


def _json(handler: BaseHTTPRequestHandler, code: int, payload: dict) -> None:
    raw = json.dumps(payload).encode()
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)


class QuietHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        return


class EntraHandler(QuietHandler):
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length:
            self.rfile.read(length)
        path = urllib.parse.urlparse(self.path).path.rstrip("/")
        if not path.endswith("/oauth2/v2.0/token"):
            _json(self, 404, {"error": "not_found"})
            return
        _json(self, 200, {
            "token_type": "Bearer",
            "expires_in": 3600,
            "access_token": GRAPH_TOKEN,
        })

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path.rstrip("/") != "/v1.0/users":
            _json(self, 404, {"error": "not_found"})
            return
        auth = self.headers.get("Authorization", "")
        if auth != f"Bearer {GRAPH_TOKEN}":
            _json(self, 401, {"error": "unauthorized"})
            return
        query = urllib.parse.parse_qs(parsed.query)
        filt = (query.get("$filter") or [""])[0]
        try:
            top = int((query.get("$top") or ["999"])[0])
        except ValueError:
            top = 999
        try:
            skip = int((query.get("$skip") or ["0"])[0])
        except ValueError:
            skip = 0
        users = ENTRA_USERS
        if "accountEnabled eq true" in filt:
            users = [user for user in users if user["accountEnabled"] is True]
        page = users[skip:skip + top]
        payload: dict = {"value": page}
        if skip + top < len(users):
            host = self.headers.get("Host", "127.0.0.1")
            nxt = urllib.parse.urlencode({
                "$filter": filt,
                "$top": str(top),
                "$skip": str(skip + top),
            })
            payload["@odata.nextLink"] = f"http://{host}/v1.0/users?{nxt}"
        _json(self, 200, payload)


class MondayHandler(QuietHandler):
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length else b""
        if urllib.parse.urlparse(self.path).path.rstrip("/") != "/v2":
            _json(self, 404, {"errors": [{"message": "not found"}]})
            return
        if self.headers.get("Authorization", "").strip() == "":
            _json(self, 401, {"errors": [{"message": "missing token"}]})
            return
        try:
            body = json.loads(raw.decode() or "{}")
        except json.JSONDecodeError:
            _json(self, 400, {"errors": [{"message": "body was not json"}]})
            return
        variables = body.get("variables") or {}
        try:
            limit = int(variables.get("limit") or 100)
            page = int(variables.get("page") or 1)
        except (TypeError, ValueError):
            _json(self, 400, {"errors": [{"message": "bad pagination"}]})
            return
        active = [user for user in MONDAY_USERS if user["status"] == "ACTIVE"]
        start = max(page - 1, 0) * limit
        _json(self, 200, {"data": {"users": active[start:start + limit]}})


def _serve(server: ThreadingHTTPServer) -> None:
    server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ready-file", required=True)
    parser.add_argument("--monday", action="store_true",
                        help="also serve the Monday GraphQL stand-in")
    args = parser.parse_args()

    entra = ThreadingHTTPServer(("127.0.0.1", 0), EntraHandler)
    monday = ThreadingHTTPServer(("127.0.0.1", 0), MondayHandler) if args.monday else None
    threading.Thread(target=_serve, args=(entra,), daemon=True).start()
    if monday is not None:
        threading.Thread(target=_serve, args=(monday,), daemon=True).start()

    lines = [f"ENTRA_PORT={entra.server_address[1]}"]
    if monday is not None:
        lines.append(f"MONDAY_PORT={monday.server_address[1]}")
    with open(args.ready_file, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    threading.Event().wait()


if __name__ == "__main__":
    main()
