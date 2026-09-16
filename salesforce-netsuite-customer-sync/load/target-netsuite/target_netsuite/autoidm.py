"""Generic AutoIDM target sink class, which handles writing streams."""

from __future__ import annotations

import abc
import sys
from functools import cached_property

import backoff
import requests
from singer_sdk.sinks import RecordSink


class FatalException(Exception):  # noqa: N818
    """Exception that can't be ignored."""


class RetriableAPIError(Exception):  # noqa: N818
    """Exception for API errors that can be retried (e.g. 429 Too Many Requests)."""


class AutoIDMAuthenticator(metaclass=abc.ABCMeta):
    """Generic authenticator for AutoIDMSink instances."""

    def authenticate_request(
        self,
        request: requests.PreparedRequest,
    ) -> requests.PreparedRequest:
        """Return the request unchanged as default behavior.

        Override this function when an authenticator should modify a request (such as
        by changing its headers or parameters) to provide authentication.
        """
        return request


class AutoIDMSink(RecordSink, metaclass=abc.ABCMeta):
    """Target sink class."""

    def __init__(self, *args, **kwargs) -> AutoIDMSink:  # noqa: ANN002 ANN003
        """Creates an instance of a target sink."""
        super().__init__(*args, **kwargs)
        self.error_count: int = 0
        self.error_happened: bool = False

    @property
    def pii_safe_keys(self) -> list[str]:
        """Field names for a record specifying entries used for log-safe PII."""
        return []

    @property
    def custom_error_messages(self) -> dict[int, str]:
        """A dictionary of HTTP error codes and corresponding strings.

        Sometimes, HTTP error codes and default API log messages can be confusing or
        misleading. Specify additional context to display to the user by overriding
        this property.
        """
        return {}

    @property
    def max_errors(self) -> int:
        """Maximum number of failed records to allow before failing the target.

        Usually specified using config["max_records"].
        """
        return 0

    def pii_safe(self, record: dict) -> str:
        """Extracts log-safe personally identifiable information from a record."""
        return ", ".join(
            [
                f"{key} is {record.get(key, f'NO_{key.upper()}_PROVIDED')}"
                for key in self.pii_safe_keys
            ]
        )

    @cached_property
    def authenticator(self) -> AutoIDMAuthenticator:
        """Cached authenticator for accessing the an API."""
        return AutoIDMAuthenticator()

    def check_if_present(self, key: str | list, record: dict) -> None:
        """Checks if a given key is in a given record and raises an error if not."""
        if key not in record:
            error_msg = (
                f"Record must have a value for `{key}`. Record: "
                f"{self.pii_safe(record)}."
            )
            raise RuntimeError(error_msg)

    def process_record(self, record: dict, context: dict) -> None:
        """Process the record and add error checking logic.

        All exceptions from called functions should be caught here and dealt with
        appropriately—either registered, if they're noncritical, or reraised so the SDK
        handles target failure. If exceptions are being reraised, final_log_messages()
        should also be called (normally this would be called during clean_up(), but the
        the SDK will not call clean_up() if it receives an exception from this
        function).

        Args:
            record: Individual record in the stream.
            context: Stream partition or context dictionary.
        """
        try:
            self.autoidm_process(record, context)
        except FatalException as e:
            error_msg = (
                f"Fatal exception occurred, so {self.max_errors=} has been "
                "ignored and target is failing regardless of current error count."
            )
            self.final_log_messages()
            raise RuntimeError(error_msg) from e
        except Exception as e:  # noqa: BLE001
            try:
                self.register_error(e)
            except RuntimeError:
                self.final_log_messages()
                raise

    @abc.abstractmethod
    def autoidm_process(self, record: dict, context: dict) -> None:
        """Process a record AutoIDM-style."""

    @backoff.on_exception(
        backoff.expo,
        (RetriableAPIError, requests.exceptions.ConnectionError, requests.exceptions.ReadTimeout),
        max_tries=5,
        factor=2,
        jitter=backoff.random_jitter,
    )
    def request(
        self,
        path: str,
        request_type: str,
        body: str | None = None,
        always_fatal: bool = False,  # noqa: FBT001 FBT002
    ) -> requests.Response:
        """Send a request to the EHSInsight API and handle resulting errors."""
        url = self.url_base + path
        headers = {"Content-Type": "application/json"}
        timeout = self.config["api_timeout"]
        req = requests.Request(method=request_type, url=url, headers=headers, json=body)
        self.authenticator.authenticate_request(req)
        response = self.request_session.send(req.prepare(), timeout=timeout)
        self.log_raw_response(response)
        self.custom_error(response.status_code)
        try:
            response.raise_for_status()
        except Exception as e:
            if response.status_code == requests.codes.unauthorized or always_fatal:
                raise FatalException from e
            if response.status_code == 429:
                raise RetriableAPIError(f"429 Too Many Requests: {response.content}") from e
            raise
        return response

    def log_raw_response(self, response: requests.Response) -> None:
        """Log the content of an API response."""
        self.logger.info("Raw response: %s", response.content)

    def custom_error(self, error_code: int) -> None:
        """Print a custom error message based on an HTTP error code."""
        if error_code in self.custom_error_messages:
            self.logger.error(self.custom_error_messages[error_code])

    def register_error(self, error_msg: str) -> None:
        """Register that an error occured, to be addressed during clean_up.

        Going over the maximum number of record failures allowed in config will cause
        the target to fail and end early.
        """
        self.logger.error("Error in request: %s", error_msg)
        self.error_count += 1
        self.error_happened = True

        if self.max_errors >= 0 and self.error_count > self.max_errors:
            error_msg = (
                f"We went over the limit of {self.max_errors=} record failures, so the "
                "run stopped early."
            )
            raise RuntimeError(error_msg)

    def final_log_messages(self) -> None:
        """Print final log messages, just before the target finishes (or fails)."""
        if self.error_happened:
            self.logger.error(
                "Error happened during run. We had this many record failures: %s",
                self.error_count,
            )
        else:
            self.logger.info("Run completed successfully.")

    @cached_property
    def request_session(self) -> requests.Session:
        """Cached session from the requests library."""
        return requests.Session()

    def clean_up(self) -> None:
        """Perform any clean up actions required at end of a stream."""
        self.final_log_messages()
        if self.error_happened:
            sys.exit(1)
