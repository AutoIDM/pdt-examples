"""SOAP client handling, including NetSuiteSOAPStream base class."""

from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import Any

import requests
from singer_sdk.streams import RESTStream

from tap_netsuite.auth import NetsuiteSOAPPassportHandler



class NetSuiteSOAPStream(RESTStream, metaclass=ABCMeta):
    """Access the Netsuite SOAP API using Token-Based Authentication.

    It's easier to inherit from RESTStream and override its methods (essentially just
    treating it as HTTPStream) than to inherit from Stream and build from scratch.
    """

    # Two major versions per year, with the last 3 years being fully supported, and the
    # last 7 years being available without support as legacy endpoints.
    # Docs: https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_N3418174.html
    WSDL_MAJOR_VERSION = "2024_1"

    def backoff_max_tries(self) -> int:
        """Return max retry attempts for HTTP requests.

        Singer SDK includes the first request attempt in this count.
        """
        return 10

    @property
    def rest_method(self) -> str:
        return "POST"

    @property
    def url_base(self) -> str:
        """
        Dynamic URL discovery is not needed for our use-case.
        Docs: https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/chapter_157011836591.html
        """
        account_id: str = self.config["account_id"]
        # Account IDs for Sandbox and Release Preview accounts need to be reformatted
        # for URLs.
        # Docs: https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_1498754928.html
        account_id = account_id.lower().replace("_", "-")
        return f"https://{account_id}.suitetalk.api.netsuite.com/services/NetSuitePort_{self.WSDL_MAJOR_VERSION}"

    @property
    def path(self) -> None:
        """All SOAP endpoints use the same URL, but `path` has to exist for the SDK."""

    def prepare_request(
        self, context: dict | None, next_page_token: Any | None
    ) -> requests.PreparedRequest:
        """Override to use `data=request_data` instead of `json=request_data`."""

        http_method = self.rest_method
        url: str = self.get_url(context)
        params: dict | str = self.get_url_params(context, next_page_token)
        request_data = self.prepare_request_payload(context, next_page_token)
        headers = self.http_headers

        return self.build_prepared_request(
            method=http_method,
            url=url,
            params=params,
            headers=headers,
            data=request_data,
        )

    @property
    @abstractmethod
    def soap_action(self) -> str:
        """Value for the SOAPAction header."""

    @property
    def http_headers(self) -> dict:
        headers = {}
        headers["Accept"] = "application/xml"
        headers["Content-Type"] = "application/xml"
        headers["SOAPAction"] = self.soap_action
        return headers

    @property
    def passport_handler(self) -> NetsuiteSOAPPassportHandler:
        """Abstracts away authentication to a different class."""
        return NetsuiteSOAPPassportHandler(
            config=self.config,
            wsdl_major_version=self.WSDL_MAJOR_VERSION,
        )

    @abstractmethod
    def soap_body(
        self, context: dict, next_page_token: Any | None
    ) -> str:
        """Value that goes in <soapenv:Body>."""

    def prepare_request_payload(
        self, context: dict | None, next_page_token: Any | None
    ) -> dict | None:
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<soapenv:Envelope xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns="http://www.w3.org/2001/XMLSchema">'  # noqa: E501
            "<soapenv:Header>"
            f"{self.passport_handler.generate_passport()}"
            "</soapenv:Header>"
            "<soapenv:Body>"
            f"{self.soap_body(context=context, next_page_token=next_page_token)}"
            "</soapenv:Body>"
            "</soapenv:Envelope>"
        )
