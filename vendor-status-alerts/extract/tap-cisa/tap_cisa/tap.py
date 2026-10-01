"""CISA advisories (RSS) and the Known Exploited Vulnerabilities catalog (JSON).

Both are public. The RSS feed holds the latest advisories only, so the
target keeps older ones by primary key.
"""

from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import requests
from singer_sdk import Stream, Tap
from singer_sdk import typing as th

ADVISORIES_URL = "https://www.cisa.gov/cybersecurity-advisories/all.xml"
KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
CVE_URL = "https://www.cve.org/CVERecord?id={cve}"


def fetch(url: str) -> requests.Response:
    # The CISA site answers 403 to some User-Agent values, for example "Mozilla/5.0".
    # The default one from requests gets 200.
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    return response


def advisory_rows(xml_text: str):
    channel = ET.fromstring(xml_text).find("channel")
    for item in channel.findall("item"):
        link = item.findtext("link") or ""
        # Links look like https://www.cisa.gov/news-events/ics-advisories/icsa-26-274-01.
        parts = link.split("/news-events/", 1)[-1].split("/")
        summary = html.unescape(re.sub(r"<[^>]+>", " ", item.findtext("description") or ""))
        yield {
            "link": link,
            "advisory_type": parts[0] if len(parts) > 1 else None,
            "title": (item.findtext("title") or "").strip(),
            "summary": re.sub(r"\s+", " ", summary).strip()[:2000],
            "published_at": parsedate_to_datetime(item.findtext("pubDate")).isoformat(),
        }


def kev_rows(catalog: dict):
    for vuln in catalog.get("vulnerabilities") or []:
        yield {
            "cve_id": vuln["cveID"],
            "vendor_project": vuln.get("vendorProject"),
            "product": vuln.get("product"),
            "vulnerability_name": vuln.get("vulnerabilityName"),
            "date_added": vuln.get("dateAdded"),
            "short_description": vuln.get("shortDescription"),
            "required_action": vuln.get("requiredAction"),
            "due_date": vuln.get("dueDate"),
            "known_ransomware_campaign_use": vuln.get("knownRansomwareCampaignUse"),
            "notes": vuln.get("notes"),
            "cwes": vuln.get("cwes") or [],
            "url": CVE_URL.format(cve=vuln["cveID"]),
        }


class AdvisoriesStream(Stream):
    name = "advisories"
    primary_keys = ("link",)
    schema = th.PropertiesList(
        th.Property("link", th.StringType, required=True),
        th.Property("advisory_type", th.StringType, description="alerts, cybersecurity-advisories, ics-advisories, ..."),
        th.Property("title", th.StringType),
        th.Property("summary", th.StringType),
        th.Property("published_at", th.DateTimeType),
    ).to_dict()

    def get_records(self, context):
        yield from advisory_rows(fetch(ADVISORIES_URL).text)


class KnownExploitedVulnerabilitiesStream(Stream):
    name = "known_exploited_vulnerabilities"
    primary_keys = ("cve_id",)
    schema = th.PropertiesList(
        th.Property("cve_id", th.StringType, required=True),
        th.Property("vendor_project", th.StringType),
        th.Property("product", th.StringType),
        th.Property("vulnerability_name", th.StringType),
        th.Property("date_added", th.DateType),
        th.Property("short_description", th.StringType),
        th.Property("required_action", th.StringType),
        th.Property("due_date", th.DateType),
        th.Property("known_ransomware_campaign_use", th.StringType),
        th.Property("notes", th.StringType),
        th.Property("cwes", th.ArrayType(th.StringType)),
        th.Property("url", th.StringType),
    ).to_dict()

    def get_records(self, context):
        yield from kev_rows(fetch(KEV_URL).json())


class TapCisa(Tap):
    name = "tap-cisa"
    config_jsonschema = th.PropertiesList().to_dict()

    def discover_streams(self):
        return [AdvisoriesStream(self), KnownExploitedVulnerabilitiesStream(self)]
