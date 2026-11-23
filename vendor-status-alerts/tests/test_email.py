"""The email template and render-email, against the tap samples. No network.

Run from this folder's parent with:
    uv run --with pytest --with singer-sdk~=0.54.7 --with requests --with msal --with cryptography \
        --with jinja2 --with duckdb==1.5.5 --with pytz pytest tests
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb

APP = Path(__file__).resolve().parent.parent
FIXTURES = APP / "tests" / "fixtures"
TEMPLATE = APP / "email" / "digest.html.j2"
for folder in ("extract/tap-adobe-status", "extract/tap-cisa", "extract/tap-ms365-service-health", "notify"):
    sys.path.insert(0, str(APP / folder))

from tap_adobe_status.tap import event_rows  # noqa: E402
from tap_cisa.tap import advisory_rows, kev_rows  # noqa: E402
from tap_ms365_service_health.tap import issue_row, message_row  # noqa: E402
from vendor_status_notify import render as render_email  # noqa: E402


def item(source, row, item_id, title, url, updated_at, status=None):
    return {"source": source, "item_id": item_id, "status": status, "title": title, "url": url,
            "updated_at": updated_at.replace("Z", "+00:00"), "data": row}


def sample_items() -> list[dict]:
    items = []
    for r in event_rows(json.loads((FIXTURES / "adobe_status_events.json").read_text())):
        items.append(item("adobe", r, r["event_id"], f"{r['product_name']}: {r['title']}", r["url"], r["updated_at"], r["status"]))
    for r in advisory_rows((FIXTURES / "cisa_advisories.xml").read_text()):
        items.append(item("cisa_advisories", r, r["link"], r["title"], r["link"], r["published_at"]))
    for r in kev_rows(json.loads((FIXTURES / "cisa_kev.json").read_text())):
        items.append(item("cisa_kev", r, r["cve_id"], r["cve_id"], r["url"], r["date_added"]))
    ms = json.loads((FIXTURES / "ms365_service_health.json").read_text())
    r = issue_row(ms["issues"][0])
    items.append(item("ms365_issues", r, r["id"], r["title"], r["url"], r["updated_at"], r["status"]))
    r = message_row(ms["messages"][0])
    items.append(item("ms365_messages", r, r["id"], r["title"], r["url"], r["updated_at"]))
    return items


def test_every_source_has_a_section():
    items = sample_items()
    subject, html = render_email.render(items, TEMPLATE)
    assert subject == f"Vendor status: {len(items)} new updates"
    for heading in ("Microsoft 365 service health (1)", "Microsoft 365 Message center (1)", "Adobe (6)",
                    "CISA known exploited vulnerabilities (2)", "CISA advisories (3)"):
        assert heading in html
    assert all(f'href="{i["url"]}"' in html for i in items)
    assert "Latest update:</b> We are rolling back a recent change." in html


def test_subject_is_singular_for_one_item():
    subject, _ = render_email.render(sample_items()[:1], TEMPLATE)
    assert subject == "Vendor status: 1 new update"


def test_values_are_escaped_and_unknown_sources_still_show():
    odd = item("someday", {}, "x", "<script>alert(1)</script>", "https://example.com/x", "2026-10-01T00:00:00Z")
    _, html = render_email.render([odd], TEMPLATE)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "someday (1)" in html


def test_main_writes_one_email_row_or_none(tmp_path, monkeypatch):
    db = tmp_path / "vendor_status.duckdb"
    with duckdb.connect(str(db)) as con:
        con.execute("create schema autoidm")
        con.execute("create table autoidm.unsent_send_once_notifications (hash varchar, source varchar, item_id varchar,"
                    " status varchar, title varchar, url varchar, updated_at timestamptz, data json)")
        for i in sample_items()[:3]:
            con.execute("insert into autoidm.unsent_send_once_notifications values ('h', ?, ?, ?, ?, ?, ?, ?)",
                        [i["source"], i["item_id"], i["status"], i["title"], i["url"], i["updated_at"], json.dumps(i["data"])])
    (tmp_path / "email").mkdir()
    (tmp_path / "email" / TEMPLATE.name).write_text(TEMPLATE.read_text())
    monkeypatch.setenv("DUCKDB_PATH", str(db))
    monkeypatch.setenv("MELTANO_PROJECT_ROOT", str(tmp_path))

    render_email.main()
    with duckdb.connect(str(db)) as con:
        rows = con.execute("select title, body from autoidm.notification_email").fetchall()
        assert len(rows) == 1 and rows[0][0] == "Vendor status: 3 new updates"
        assert (tmp_path / ".pdt" / "email-preview.html").read_text() == rows[0][1]
        con.execute("delete from autoidm.unsent_send_once_notifications")

    render_email.main()
    with duckdb.connect(str(db)) as con:
        assert con.execute("select count(*) from autoidm.notification_email").fetchone()[0] == 0
