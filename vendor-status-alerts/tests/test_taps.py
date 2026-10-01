"""Parsers of the three taps, against saved samples. No network.

Run from this folder's parent with:
    uv run --with pytest --with singer-sdk~=0.54.7 --with msal --with cryptography pytest tests
"""

from __future__ import annotations

import base64
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12, BestAvailableEncryption
from cryptography.x509.oid import NameOID

APP = Path(__file__).resolve().parent.parent
FIXTURES = APP / "tests" / "fixtures"
for tap in ("tap-adobe-status", "tap-cisa", "tap-ms365-service-health"):
    sys.path.insert(0, str(APP / "extract" / tap))

from tap_adobe_status.tap import event_rows, plain  # noqa: E402
from tap_cisa.tap import advisory_rows, kev_rows  # noqa: E402
from tap_ms365_service_health.tap import client_credential, issue_row, message_row  # noqa: E402


def test_adobe_one_row_per_event_and_product():
    rows = list(event_rows(json.loads((FIXTURES / "adobe_status_events.json").read_text())))
    keys = [(r["event_id"], r["product_id"]) for r in rows]
    assert len(keys) == len(set(keys))
    incident = next(r for r in rows if r["event_id"] == "202608040123")
    assert incident["kind"] == "incident"
    assert incident["product_name"] == "Adobe Commerce"
    assert incident["status"] == "Closed", "latest update wins"
    assert incident["update_count"] == 2
    assert incident["url"] == "https://status.adobe.com/products/503473/202608040123"
    assert "<a" not in incident["message"]
    maintenance = [r for r in rows if r["kind"] == "maintenance"]
    assert maintenance and all("{" not in r["message"] for r in maintenance), "time placeholders filled"


def test_adobe_plain_text_keeps_line_breaks():
    assert plain("<p>One</p><p>Two {startDateTime}</p>", "2026-01-01", None) == "One\nTwo 2026-01-01"


def test_cisa_advisories():
    rows = list(advisory_rows((FIXTURES / "cisa_advisories.xml").read_text()))
    assert {r["advisory_type"] for r in rows} == {"ics-advisories", "alerts"}
    assert all(r["title"] == r["title"].strip() for r in rows)
    assert all(r["published_at"].endswith("+00:00") for r in rows)


def test_cisa_kev():
    rows = list(kev_rows(json.loads((FIXTURES / "cisa_kev.json").read_text())))
    assert rows[0]["url"] == f"https://www.cve.org/CVERecord?id={rows[0]['cve_id']}"
    assert isinstance(rows[0]["cwes"], list)


def test_ms365_rows():
    sample = json.loads((FIXTURES / "ms365_service_health.json").read_text())
    issue = issue_row(sample["issues"][0])
    assert issue["latest_post"] == "We are rolling back a recent change.", "newest post by time"
    assert issue["url"].endswith("/EX123456")
    message = message_row(sample["messages"][0])
    assert message["services"] == ["Microsoft Teams"]
    assert message["body"] == "<p>We will retire the feature.</p>"


def self_signed_pfx(password: bytes) -> bytes:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test")])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(1).not_valid_before(now).not_valid_after(now + timedelta(days=1))
            .sign(key, hashes.SHA256()))
    return pkcs12.serialize_key_and_certificates(b"test", key, cert, None, BestAvailableEncryption(password))


def test_ms365_certificate_wins_over_secret(tmp_path):
    pfx = self_signed_pfx(b"pw")
    from_b64 = client_credential({"private_key_b64": base64.b64encode(pfx).decode(), "private_key_password": "pw",
                                  "client_secret": "ignored"})
    assert from_b64["private_key"].startswith("-----BEGIN PRIVATE KEY-----")
    assert len(from_b64["thumbprint"]) == 40
    path = tmp_path / "app.pfx"
    path.write_bytes(pfx)
    assert client_credential({"private_key_path": str(path), "private_key_password": "pw"}) == from_b64
    assert client_credential({"client_secret": "s"}) == "s"
    with pytest.raises(ValueError):
        client_credential({})
