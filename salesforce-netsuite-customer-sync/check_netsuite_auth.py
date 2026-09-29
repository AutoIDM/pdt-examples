#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["pyjwt", "cryptography", "pytz", "requests", "python-dotenv"]
# ///
"""Check NetSuite OAuth 2.0 client-credentials auth, the way tap-netsuite does it.

Reads the same env vars the tap reads, from .env in this folder or any parent:
  TAP_NETSUITE_ACCOUNT_ID, TAP_NETSUITE_CLIENT_ID,
  TAP_NETSUITE_CERTIFICATE_ID, TAP_NETSUITE_PRIVATE_KEY

Run it, change your NetSuite setup, run it again. It prints no secret values,
only lengths, fingerprints and the first and last four characters of the two
identifiers you need to eyeball against the NetSuite UI.

Exit codes: 0 auth works, 1 local config problem, 2 NetSuite rejected the token
request, 3 auth worked but customer or contact is not readable.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import json
import os
import pathlib
import sys

import jwt
import pytz
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from dotenv import load_dotenv

EXIT_OK = 0
EXIT_CONFIG = 1
EXIT_TOKEN = 2
EXIT_RECORD = 3

REQUIRED = [
    "TAP_NETSUITE_ACCOUNT_ID",
    "TAP_NETSUITE_CLIENT_ID",
    "TAP_NETSUITE_CERTIFICATE_ID",
    "TAP_NETSUITE_PRIVATE_KEY",
]


def ends(value: str) -> str:
    if len(value) <= 8:
        return "(too short to mask)"
    return f"{value[:4]}...{value[-4:]}"


def load_env() -> None:
    here = pathlib.Path(__file__).resolve().parent
    for folder in [here, *here.parents]:
        candidate = folder / ".env"
        if candidate.is_file():
            load_dotenv(candidate, override=False)
            print(f"  loaded {candidate}")


def read_private_key(raw: str) -> bytes:
    as_path = pathlib.Path(raw)
    if as_path.is_file():
        print(f"  private key source: file at {as_path}")
        return as_path.read_bytes()
    if "/" in raw and len(raw) < 300:
        print(f"  private key source: looks like a path, but {as_path} does not exist")
        print("  note: a relative path resolves against the working directory")
        sys.exit(EXIT_CONFIG)
    print(f"  private key source: raw text, {len(raw)} characters")
    return raw.encode("utf-8")


def describe_key(key_bytes: bytes):
    try:
        key = serialization.load_pem_private_key(key_bytes, password=None)
    except ValueError as e:
        print(f"  FAIL the private key did not parse as PEM: {e}")
        print("  check for escaped \\n in .env, or a truncated file")
        sys.exit(EXIT_CONFIG)

    public_der = key.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    fingerprint = hashlib.sha256(public_der).hexdigest()[:32]
    print(f"  public key sha256 (first 32 hex): {fingerprint}")

    if not isinstance(key, ec.EllipticCurvePrivateKey):
        print(f"  FAIL key type is {type(key).__name__}, but the tap signs with ES256")
        print("  ES256 needs an EC P-256 key. An RSA key cannot be used here.")
        sys.exit(EXIT_CONFIG)

    curve = key.curve.name
    print(f"  key type: EC, curve {curve}")
    if curve != "secp256r1":
        print(f"  FAIL ES256 requires secp256r1 (P-256), not {curve}")
        sys.exit(EXIT_CONFIG)
    return key


def main() -> int:
    print("env files")
    load_env()

    print("\nconfig")
    missing = [name for name in REQUIRED if not os.environ.get(name, "").strip()]
    if missing:
        for name in missing:
            print(f"  FAIL {name} is not set")
        return EXIT_CONFIG

    account_id = os.environ["TAP_NETSUITE_ACCOUNT_ID"].strip()
    client_id = os.environ["TAP_NETSUITE_CLIENT_ID"].strip()
    certificate_id = os.environ["TAP_NETSUITE_CERTIFICATE_ID"].strip()

    print(f"  account_id:     {account_id}")
    print(f"  client_id:      {ends(client_id)}  ({len(client_id)} chars)")
    print(f"  certificate_id: {ends(certificate_id)}  ({len(certificate_id)} chars)")
    print(f"  account looks like: {'production' if account_id.isdigit() else 'sandbox or release preview'}")

    print("\nprivate key")
    key_bytes = read_private_key(os.environ["TAP_NETSUITE_PRIVATE_KEY"].strip())
    describe_key(key_bytes)

    host_id = account_id.lower().replace("_", "-")
    url_base = f"https://{host_id}.suitetalk.api.netsuite.com/services/rest"
    token_url = f"{url_base}/auth/oauth2/v1/token"

    print("\njwt")
    now = datetime.datetime.now(tz=pytz.utc)
    assertion = jwt.encode(
        payload={
            "iss": client_id,
            "scope": "restlets,rest_webservices,suite_analytics",
            "aud": token_url,
            "exp": now + datetime.timedelta(hours=1),
            "iat": now,
        },
        key=key_bytes,
        algorithm="ES256",
        headers={"kid": certificate_id},
    )
    header = json.loads(base64.urlsafe_b64decode(assertion.split(".")[0] + "=="))
    print(f"  header: {header}")
    print(f"  aud:    {token_url}")

    print("\ntoken exchange")
    resp = requests.post(
        token_url,
        data={
            "grant_type": "client_credentials",
            "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
            "client_assertion": assertion,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=60,
    )
    print(f"  POST {token_url}")
    print(f"  status: {resp.status_code}")
    print(f"  body:   {resp.text[:400]}")

    if not resp.ok:
        print("\n  NetSuite rejected the request. Things to check, most likely first:")
        print("  1. The integration record has 'Client Credentials (Machine to Machine) Grant' enabled.")
        print("  2. The certificate for this certificate_id is uploaded at")
        print("     Setup > Integration > OAuth 2.0 Client Credentials (M2M) Setup,")
        print("     and its public key matches the fingerprint printed above.")
        print("  3. That mapping names the same integration record as this client_id,")
        print("     plus an entity and a role that hold the REST Web Services permission.")
        print("  4. account_id is right, including the '-sb1' style suffix for a sandbox.")
        print("  NetSuite reports most of these as a generic 500 server_error.")
        return EXIT_TOKEN

    access_token = resp.json()["access_token"]
    print("  OK, access token received")

    print("\nrecord access")
    failed = False
    auth_header = {"Authorization": f"Bearer {access_token}"}
    for record in ("customer", "contact"):
        r = requests.get(
            f"{url_base}/record/v1/{record}",
            params={"limit": 1},
            headers=auth_header,
            timeout=60,
        )
        if r.ok:
            print(f"  {record:9} {r.status_code}  totalResults={r.json().get('totalResults')}")
        else:
            failed = True
            print(f"  {record:9} {r.status_code}  {r.text[:200]}")

    if failed:
        print("\n  Auth works but a record type is not readable.")
        print("  Add 'Lists > Customers' and 'Lists > Contacts' at level Full to the role.")
        print("  Permission changes can take up to 24 hours to apply.")
        return EXIT_RECORD

    print("\nall checks passed")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
