"""Microsoft 365 service health for one tenant, from Microsoft Graph.

The app registration needs the application permissions ServiceHealth.Read.All
and ServiceMessage.Read.All, with admin consent. It signs in with a client
secret or with a certificate (a PFX file, or the same file as base64).
"""

from __future__ import annotations

import base64
from pathlib import Path

import msal
import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs12
from singer_sdk import Stream, Tap
from singer_sdk import typing as th

GRAPH = "https://graph.microsoft.com/v1.0/admin/serviceAnnouncement"
ISSUE_URL = "https://admin.cloud.microsoft/#/servicehealth/:/alerts/{id}"
MESSAGE_URL = "https://admin.cloud.microsoft/#/MessageCenter/:/messages/{id}"


def certificate_credential(pfx: bytes, password: str | None) -> dict:
    key, cert, _ = pkcs12.load_key_and_certificates(pfx, password.encode() if password else None)
    return {
        "private_key": key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        ).decode(),
        "thumbprint": cert.fingerprint(hashes.SHA1()).hex(),
    }


def client_credential(config: dict):
    """A certificate wins over a client secret, and base64 wins over a path."""
    password = config.get("private_key_password")
    if config.get("private_key_b64"):
        return certificate_credential(base64.b64decode(config["private_key_b64"]), password)
    if config.get("private_key_path"):
        return certificate_credential(Path(config["private_key_path"]).read_bytes(), password)
    if config.get("client_secret"):
        return config["client_secret"]
    raise ValueError("set client_secret, private_key_b64, or private_key_path")


def graph_token(config: dict) -> str:
    app = msal.ConfidentialClientApplication(
        config["client_id"],
        authority=f"https://login.microsoftonline.com/{config['tenant_id']}",
        client_credential=client_credential(config),
    )
    result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    if "access_token" not in result:
        raise RuntimeError(f"Entra sign-in failed: {result.get('error')}: {result.get('error_description')}")
    return result["access_token"]


def issue_row(issue: dict) -> dict:
    posts = sorted(issue.get("posts") or [], key=lambda post: post.get("createdDateTime") or "")
    latest = posts[-1] if posts else {}
    return {
        "id": issue["id"],
        "title": issue.get("title"),
        "service": issue.get("service"),
        "feature": issue.get("feature"),
        "feature_group": issue.get("featureGroup"),
        "classification": issue.get("classification"),
        "status": issue.get("status"),
        "impact_description": issue.get("impactDescription"),
        "is_resolved": issue.get("isResolved"),
        "origin": issue.get("origin"),
        "start_at": issue.get("startDateTime"),
        "end_at": issue.get("endDateTime"),
        "updated_at": issue.get("lastModifiedDateTime"),
        "latest_post": (latest.get("description") or {}).get("content"),
        "url": ISSUE_URL.format(id=issue["id"]),
    }


def message_row(message: dict) -> dict:
    return {
        "id": message["id"],
        "title": message.get("title"),
        "category": message.get("category"),
        "severity": message.get("severity"),
        "services": message.get("services") or [],
        "tags": message.get("tags") or [],
        "is_major_change": message.get("isMajorChange"),
        "action_required_by": message.get("actionRequiredByDateTime"),
        "start_at": message.get("startDateTime"),
        "end_at": message.get("endDateTime"),
        "updated_at": message.get("lastModifiedDateTime"),
        "body": (message.get("body") or {}).get("content"),
        "url": MESSAGE_URL.format(id=message["id"]),
    }


def overview_row(overview: dict) -> dict:
    return {"id": overview["id"], "service": overview.get("service"), "status": overview.get("status")}


class GraphStream(Stream):
    path = ""
    row = None

    def get_records(self, context):
        token = self._tap.token()
        url = f"{GRAPH}/{self.path}"
        while url:
            response = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=120)
            if response.status_code == 403:
                raise RuntimeError(
                    "Microsoft Graph refused access. Give the app registration the application permissions "
                    "ServiceHealth.Read.All and ServiceMessage.Read.All, then grant admin consent."
                )
            response.raise_for_status()
            page = response.json()
            for item in page.get("value") or []:
                yield type(self).row(item)
            url = page.get("@odata.nextLink")


class IssuesStream(GraphStream):
    name = "issues"
    path = "issues"
    row = staticmethod(issue_row)
    primary_keys = ("id",)
    schema = th.PropertiesList(
        th.Property("id", th.StringType, required=True),
        th.Property("title", th.StringType),
        th.Property("service", th.StringType),
        th.Property("feature", th.StringType),
        th.Property("feature_group", th.StringType),
        th.Property("classification", th.StringType, description="incident or advisory"),
        th.Property("status", th.StringType),
        th.Property("impact_description", th.StringType),
        th.Property("is_resolved", th.BooleanType),
        th.Property("origin", th.StringType),
        th.Property("start_at", th.DateTimeType),
        th.Property("end_at", th.DateTimeType),
        th.Property("updated_at", th.DateTimeType),
        th.Property("latest_post", th.StringType),
        th.Property("url", th.StringType),
    ).to_dict()


class MessagesStream(GraphStream):
    name = "messages"
    path = "messages"
    row = staticmethod(message_row)
    primary_keys = ("id",)
    schema = th.PropertiesList(
        th.Property("id", th.StringType, required=True),
        th.Property("title", th.StringType),
        th.Property("category", th.StringType, description="preventOrFix, planForChange, or stayInformed"),
        th.Property("severity", th.StringType),
        th.Property("services", th.ArrayType(th.StringType)),
        th.Property("tags", th.ArrayType(th.StringType)),
        th.Property("is_major_change", th.BooleanType),
        th.Property("action_required_by", th.DateTimeType),
        th.Property("start_at", th.DateTimeType),
        th.Property("end_at", th.DateTimeType),
        th.Property("updated_at", th.DateTimeType),
        th.Property("body", th.StringType),
        th.Property("url", th.StringType),
    ).to_dict()


class HealthOverviewsStream(GraphStream):
    name = "health_overviews"
    path = "healthOverviews"
    row = staticmethod(overview_row)
    primary_keys = ("id",)
    schema = th.PropertiesList(
        th.Property("id", th.StringType, required=True),
        th.Property("service", th.StringType),
        th.Property("status", th.StringType),
    ).to_dict()


class TapMs365ServiceHealth(Tap):
    name = "tap-ms365-service-health"
    config_jsonschema = th.PropertiesList(
        th.Property("tenant_id", th.StringType, required=True),
        th.Property("client_id", th.StringType, required=True),
        th.Property("client_secret", th.StringType, secret=True),
        th.Property("private_key_b64", th.StringType, secret=True, description="Base64 of the PFX file"),
        th.Property("private_key_path", th.StringType, description="Path to the PFX file"),
        th.Property("private_key_password", th.StringType, secret=True),
    ).to_dict()
    _token = None

    def token(self) -> str:
        if self._token is None:
            self._token = graph_token(self.config)
        return self._token

    def discover_streams(self):
        return [IssuesStream(self), MessagesStream(self), HealthOverviewsStream(self)]
