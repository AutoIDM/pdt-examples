"""Adobe incidents and maintenance from the feed that status.adobe.com reads.

The documented Adobe Status API needs an Adobe Developer Console project.
The status page itself reads one public JSON document with every event of
the last 40 days, so this tap reads that and needs no credentials.
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone

import requests
from singer_sdk import Stream, Tap
from singer_sdk import typing as th

FEED_URL = "https://data.status.adobe.com/adobestatus/StatusEvents"
EVENT_URL = "https://status.adobe.com/products/{product_id}/{event_id}"
EVENT_KINDS = {"incident": ("incidentEvent", "incidents"), "maintenance": ("maintenanceEvent", "maintenance")}


def epoch(value) -> str | None:
    seconds = int(value or 0)
    if seconds <= 0:
        return None
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat()


def plain(text: str | None, start: str | None, end: str | None) -> str | None:
    """The status page's message as plain text, with its time placeholders filled."""
    if text is None:
        return None
    def shown(value: str | None) -> str:
        return datetime.fromisoformat(value).strftime("%b %d, %Y %H:%M UTC") if value else ""

    text = text.replace("{startDateTime}", shown(start)).replace("{endDateTime}", shown(end))
    text = re.sub(r"<br\s*/?>|</(p|li|div)>", "\n", text, flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", "", text))
    return re.sub(r"\n\s*\n+", "\n", text).strip()


def event_rows(feed: dict, locale: str = "en"):
    """One row per event and product, carrying that product's latest update."""
    for kind, (section, key) in EVENT_KINDS.items():
        body = feed.get(section) or {}
        texts = (body.get("messages") or {}).get(locale) or {}

        def text(token: str) -> str | None:
            entry = texts.get(token) or {}
            return entry.get("htmlMessage") or entry.get("textMessage")

        for event in (body.get(key) or {}).values():
            clouds = event.get("clouds") or {}
            services = event.get("services") or {}
            for product in (event.get("products") or {}).values():
                history = product.get("history") or {}
                if not history:
                    continue
                updates = [history[t] for t in sorted(history, key=int)]
                latest = updates[-1]
                start = epoch(product.get("startedOn") or event.get("startedOn") or event.get("scheduledDate"))
                end = epoch(product.get("endedOn") or event.get("completedOn"))
                cloud_names = [c["name"] for c in clouds.values() if product["id"] in (c.get("cloudProducts") or [])]
                service_ids = (latest.get("serviceImpact") or {}).get("productServices") or []
                yield {
                    "event_id": event["id"],
                    "product_id": product["id"],
                    "kind": kind,
                    "product_name": product.get("name"),
                    "cloud_name": ", ".join(cloud_names) or None,
                    "status": latest.get("status"),
                    "severity": latest.get("severity"),
                    "customer_impact": latest.get("customerImpact"),
                    "title": plain(text(latest.get("titleToken", "")), start, end),
                    "message": plain(text(latest.get("messageToken", "")), start, end),
                    "services": [services[s]["name"] for s in service_ids if s in services],
                    "regions": (latest.get("locationImpact") or {}).get("serviceRegions") or [],
                    "scheduled_at": epoch(event.get("scheduledDate")),
                    "started_at": start,
                    "ended_at": end,
                    "updated_at": epoch(latest.get("messageTime")),
                    "update_count": len(updates),
                    "url": EVENT_URL.format(product_id=product["id"], event_id=event["id"]),
                }


class EventsStream(Stream):
    name = "events"
    primary_keys = ("event_id", "product_id")
    schema = th.PropertiesList(
        th.Property("event_id", th.StringType, required=True),
        th.Property("product_id", th.StringType, required=True),
        th.Property("kind", th.StringType, description="incident or maintenance"),
        th.Property("product_name", th.StringType),
        th.Property("cloud_name", th.StringType),
        th.Property("status", th.StringType),
        th.Property("severity", th.StringType),
        th.Property("customer_impact", th.StringType),
        th.Property("title", th.StringType),
        th.Property("message", th.StringType),
        th.Property("services", th.ArrayType(th.StringType)),
        th.Property("regions", th.ArrayType(th.StringType)),
        th.Property("scheduled_at", th.DateTimeType),
        th.Property("started_at", th.DateTimeType),
        th.Property("ended_at", th.DateTimeType),
        th.Property("updated_at", th.DateTimeType),
        th.Property("update_count", th.IntegerType),
        th.Property("url", th.StringType),
    ).to_dict()

    def get_records(self, context):
        response = requests.get(FEED_URL, timeout=120)
        response.raise_for_status()
        yield from event_rows(response.json(), self.config.get("locale", "en"))


class TapAdobeStatus(Tap):
    name = "tap-adobe-status"
    config_jsonschema = th.PropertiesList(
        th.Property("locale", th.StringType, default="en", description="Language of titles and messages, for example en, de, or ja"),
    ).to_dict()

    def discover_streams(self):
        return [EventsStream(self)]
