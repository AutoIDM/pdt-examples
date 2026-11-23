"""Render email/digest.html.j2 over the unsent notifications.

Reads autoidm.unsent_send_once_notifications and replaces
autoidm.notification_email with one row (title, body) for target-apprise,
or with no row when nothing is unsent. The template sets the subject in
`{% set subject %}` and renders the HTML body. A copy of the HTML goes to
.pdt/email-preview.html, so a change to the template can be checked
before anything is sent.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import duckdb
from jinja2 import ChainableUndefined, Environment, FileSystemLoader, select_autoescape


def when(value, fmt: str = "%b %d, %Y %H:%M UTC") -> str:
    """Format a timestamp from the database or from an item's data."""
    if not value:
        return ""
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc)
    return value.strftime(fmt)


def environment(template_dir: Path) -> Environment:
    env = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(["html", "j2"]),
        undefined=ChainableUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["when"] = when
    return env


def render(items: list[dict], template_path: Path) -> tuple[str, str]:
    """The subject and the HTML body for these items."""
    sources: dict[str, list[dict]] = {}
    for item in sorted(items, key=lambda i: i["updated_at"], reverse=True):
        sources.setdefault(item["source"], []).append(item)
    template = environment(template_path.parent).get_template(template_path.name)
    context = {"sources": sources, "total": len(items), "generated_at": datetime.now(timezone.utc)}
    subject = str(template.make_module(context).subject).strip()
    return subject, template.render(context)


def unsent_items(con) -> list[dict]:
    rows = con.execute(
        "select source, item_id, status, title, url, updated_at, data"
        " from autoidm.unsent_send_once_notifications"
    ).fetchall()
    names = ["source", "item_id", "status", "title", "url", "updated_at", "data"]
    items = [dict(zip(names, row)) for row in rows]
    for item in items:
        item["data"] = json.loads(item["data"]) if item["data"] else {}
    return items


def main() -> None:
    root = Path(os.environ.get("MELTANO_PROJECT_ROOT", "."))
    with duckdb.connect(os.environ["DUCKDB_PATH"]) as con:
        items = unsent_items(con)
        con.execute("create or replace table autoidm.notification_email (title varchar, body varchar)")
        if not items:
            print("no unsent notifications")
            return
        subject, body = render(items, root / "email" / "digest.html.j2")
        con.execute("insert into autoidm.notification_email values (?, ?)", [subject, body])
    preview = root / ".pdt" / "email-preview.html"
    preview.parent.mkdir(exist_ok=True)
    preview.write_text(body)
    print(f"rendered {len(items)} items: {subject}; preview at {preview}")
