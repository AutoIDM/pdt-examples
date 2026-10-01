"""REST client handling, including NetSuiteRESTStream base class."""

from __future__ import annotations

import sys
from functools import cached_property
from typing import Any, Callable
from urllib.parse import parse_qsl

import requests
from singer_sdk.helpers.jsonpath import extract_jsonpath
from singer_sdk.pagination import BaseHATEOASPaginator, BaseOffsetPaginator
from singer_sdk.streams import RESTStream

from tap_netsuite.auth import NetSuiteRESTAuthenticator

if sys.version_info >= (3, 9):
    import importlib.resources as importlib_resources
else:
    import importlib_resources


_Auth = Callable[[requests.PreparedRequest], requests.PreparedRequest]

SCHEMAS_DIR = importlib_resources.files(__package__) / "schemas"


class NetSuiteRESTPaginator(BaseHATEOASPaginator):

    NEXT_URL_JSONPATH = "$..links[?(@.rel=='next')].href"

    def get_next_url(self, response: requests.Response) -> str | None:
        all_matches = extract_jsonpath(self.NEXT_URL_JSONPATH, response.json())
        return next(all_matches, None)


class NetSuiteRESTStream(RESTStream):
    """NetSuite stream class."""

    records_jsonpath = "$"

    def backoff_max_tries(self) -> int:
        """Return max retry attempts for HTTP requests.

        Singer SDK includes the first request attempt in this count.
        """
        return 10

    @property
    def url_base(self) -> str:
        """Return the API URL root, configurable via tap settings."""
        account_id: str = self.config["account_id"]
        # Account IDs for Sandbox and Release Preview accounts need to be reformatted
        # for URLs.
        # Docs: https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_1498754928.html
        account_id = account_id.lower().replace("_", "-")
        return f"https://{account_id}.suitetalk.api.netsuite.com/services/rest"

    @cached_property
    def authenticator(self) -> _Auth:
        return NetSuiteRESTAuthenticator.create_for_stream(self)

    @property
    def http_headers(self) -> dict:
        headers = {}
        headers["Accept"] = "application/json"
        return headers

    def response_error_message(self, response: requests.Response) -> str:
        """Include json from failed response in the message to aid with debugging"""
        message = super().response_error_message(response=response)
        response_json = None
        try:
            response_json = response.json()
        except requests.JSONDecodeError:
            response_json = "RESPONSE DOES NOT CONTAIN VALID JSON"
        return f"{message} with JSON content: {response_json}"


class NetSuiteListRESTStream(NetSuiteRESTStream):

    records_jsonpath = "$.items[*]"

    def get_new_paginator(self) -> NetSuiteRESTPaginator:
        """Create a new pagination helper instance."""
        return NetSuiteRESTPaginator()

    def get_url_params(
        self,
        context: Any | None,  # noqa: ARG002
        next_page_token: Any | None,
    ) -> dict[str, Any]:
        if next_page_token:
            return dict(parse_qsl(next_page_token.query))
        return {}


class NetSuiteSuiteQLPaginator(BaseOffsetPaginator):

    def has_more(self, response: requests.Response) -> bool:
        return response.json().get("hasMore", False)


class NetSuiteSuiteQLStream(NetSuiteRESTStream):

    path = "/query/v1/suiteql"
    rest_method = "POST"
    records_jsonpath = "$.items[*]"
    table: str

    @property
    def http_headers(self) -> dict:
        headers = super().http_headers
        headers["Prefer"] = "transient"
        return headers

    def get_new_paginator(self) -> NetSuiteSuiteQLPaginator:
        """Create a new pagination helper instance."""
        return NetSuiteSuiteQLPaginator(start_value=0, page_size=1000)

    def get_url_params(
        self,
        context: Any | None,  # noqa: ARG002
        next_page_token: Any | None,
    ) -> dict[str, Any]:
        return {"limit": 1000, "offset": next_page_token or 0}

    def prepare_request_payload(
        self,
        context: Any | None,  # noqa: ARG002
        next_page_token: Any | None,  # noqa: ARG002
    ) -> dict | None:
        columns = list(self.schema["properties"])
        return {"q": f"SELECT {', '.join(columns)} FROM {self.table}"}

    def post_process(
        self,
        row: dict,
        context: Any | None = None,  # noqa: ARG002
    ) -> dict | None:
        row.pop("links", None)
        return row
