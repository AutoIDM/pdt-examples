"""NetSuite target sink class, which handles writing streams."""

from __future__ import annotations

import json
from functools import cached_property
from typing import Any, ClassVar

import target_netsuite.autoidm as aidm
from target_netsuite.auth import NetSuiteAuthenticator

# The desired-state builders send this string to mean "clear this field in NetSuite".
BLANK_VALUE = "_blank_"


class NetSuiteSink(aidm.AutoIDMSink):
    """NetSuite target sink class."""

    @property
    def max_errors(self) -> int:
        """User-configurable allowable number of failed records."""
        return self.config["max_errors"]

    @cached_property
    def authenticator(self) -> NetSuiteAuthenticator:
        """Cached authenticator for accessing the EHSInsight API."""
        return NetSuiteAuthenticator(sink=self)

    @property
    def url_base(self) -> str:
        """Return the API URL root, configurable via target settings."""
        account_id: str = self.config["account_id"]
        # Account IDs for Sandbox and Release Preview accounts need to be reformatted
        # for URLs.
        # Docs: https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_1498754928.html
        account_id = account_id.lower().replace("_", "-")
        return f"https://{account_id}.suitetalk.api.netsuite.com/services/rest"


class NetSuiteTimeSheetSink(NetSuiteSink):

    @property
    def pii_safe_keys(self) -> list[str]:
        """Log-safe PII used to identify a time sheet."""
        return ["id", "employee"]

    def autoidm_process(self, record: dict, context: dict) -> None:  # noqa: ARG002
        """Process the record.

        Args:
            record: Individual record in the stream.
            context: Stream partition or context dictionary.
        """
        self.check_if_present("_autoidm__action", record)
        action = record.get("_autoidm__action").upper()
        pii_safe = self.pii_safe(record)

        if action not in ["CREATE", "UPDATE"]:
            error_msg = (
                "Invalid action. Must be 'CREATE' or 'UPDATE'. Time Sheet: "
                f"{pii_safe}."
            )
            raise RuntimeError(error_msg)

        if action == "UPDATE":
            self.logger.info("Attempting to update time sheet: %s.", pii_safe)
            self.check_if_present("id", record)
            fields_to_null = record.get("_autoidm__fields_to_null", [])
            timesheet = {}
            for k, v in record.items():
                if (
                    not k.startswith("_autoidm_")
                    and not k.startswith("_sdc_")
                    and v is not None
                ):
                    timesheet.update({k: v})
            for k in fields_to_null:
                timesheet.update({k: None})
            self.request(f"/record/v1/timesheet/{record['id']}", "PATCH", timesheet)
        if action == "CREATE":
            self.logger.info("Attempting to create time sheet: %s.", pii_safe)
            self.check_if_present("employee", record)
            self.check_if_present("startDate", record)
            fields_to_null = record.get("_autoidm__fields_to_null", [])
            timesheet = {}
            for k, v in record.items():
                if not k.startswith("_autoidm_") and not k.startswith("_sdc_"):
                    timesheet.update({k: v})
            for k in fields_to_null:
                timesheet.update({k: None})
            self.request("/record/v1/timesheet", "POST", timesheet)


class NetSuiteTimeBillSink(NetSuiteSink):

    @property
    def pii_safe_keys(self) -> list[str]:
        """Log-safe PII used to identify a time sheet."""
        return ["id", "timesheet", "tranDate"]

    def autoidm_process(self, record: dict, context: dict) -> None:  # noqa: ARG002
        """Process the record.

        Args:
            record: Individual record in the stream.
            context: Stream partition or context dictionary.
        """
        self.check_if_present("_autoidm__action", record)
        action = record.get("_autoidm__action").upper()
        pii_safe = self.pii_safe(record)

        if action not in ["CREATE", "UPDATE"]:
            error_msg = (
                "Invalid action. Must be 'CREATE' or 'UPDATE'. Time Bill: "
                f"{pii_safe}."
            )
            raise RuntimeError(error_msg)

        if action == "UPDATE":
            self.logger.info("Attempting to update time bill: %s.", pii_safe)
            self.check_if_present("id", record)
            fields_to_null = record.get("_autoidm__fields_to_null", [])
            timebill = {}
            for k, v in record.items():
                if (
                    not k.startswith("_autoidm_")
                    and not k.startswith("_sdc_")
                    and v is not None
                ):
                    timebill.update({k: v})
            for k in fields_to_null:
                timebill.update({k: None})
            self.request(f"/record/v1/timebill/{record['id']}", "PATCH", timebill)
        if action == "CREATE":
            self.logger.info("Attempting to create time bill: %s.", pii_safe)
            self.check_if_present("hours", record)
            self.check_if_present("memo", record)
            self.check_if_present("location", record)
            self.check_if_present("timesheet", record)
            self.check_if_present("tranDate", record)
            self.check_if_present("employee", record)
            fields_to_null = record.get("_autoidm__fields_to_null", [])
            timebill = {}
            for k, v in record.items():
                if not k.startswith("_autoidm_") and not k.startswith("_sdc_"):
                    timebill.update({k: v})
            for k in fields_to_null:
                timebill.update({k: None})
            self.request("/record/v1/timebill", "POST", timebill)


class NetSuiteRecordSink(NetSuiteSink):
    """NetSuite sink that builds a request body from a declared field mapping."""

    record_path: str
    record_label: str
    fields: ClassVar[dict[str, str]] = {}
    references: ClassVar[dict[str, str]] = {}
    sublists: ClassVar[dict[str, str]] = {}
    required_on_create: ClassVar[list[str]] = []

    def build_body(self, record: dict, action: str) -> dict:
        """Build a NetSuite request body from the declared source columns.

        Args:
            record: Individual record in the stream.
            action: Either `CREATE` or `UPDATE`.
        """
        body: dict[str, Any] = {}
        mappings = (
            (self.fields, lambda value: value),
            (self.references, lambda value: {"id": str(value)}),
            (self.sublists, lambda value: {"items": json.loads(value)}),
        )
        for mapping, wrap in mappings:
            for source, netsuite_field in mapping.items():
                value = record.get(source)
                if value == BLANK_VALUE:
                    body[netsuite_field] = None
                elif value is None:
                    # On an update, an absent value must not null out what NetSuite
                    # already holds.
                    if action == "CREATE":
                        body[netsuite_field] = None
                else:
                    body[netsuite_field] = wrap(value)
        for netsuite_field in record.get("_autoidm__fields_to_null", []):
            body[netsuite_field] = None
        return body

    def autoidm_process(self, record: dict, context: dict) -> None:  # noqa: ARG002
        """Process the record.

        Args:
            record: Individual record in the stream.
            context: Stream partition or context dictionary.
        """
        self.check_if_present("_autoidm__action", record)
        action = record["_autoidm__action"].upper()
        pii_safe = self.pii_safe(record)
        label = self.record_label.lower()

        if action not in ["CREATE", "UPDATE"]:
            error_msg = (
                "Invalid action. Must be 'CREATE' or 'UPDATE'. "
                f"{self.record_label}: {pii_safe}."
            )
            raise RuntimeError(error_msg)

        if action == "CREATE":
            self.logger.info("Attempting to create %s: %s.", label, pii_safe)
            for source in self.required_on_create:
                self.check_if_present(source, record)
            body = self.build_body(record, action)
            self.request(f"/record/v1/{self.record_path}", "POST", body)
        if action == "UPDATE":
            self.logger.info("Attempting to update %s: %s.", label, pii_safe)
            self.check_if_present("id", record)
            body = self.build_body(record, action)
            self.request(f"/record/v1/{self.record_path}/{record['id']}", "PATCH", body)


class NetSuiteCustomerSink(NetSuiteRecordSink):

    record_path = "customer"
    record_label = "Customer"
    fields: ClassVar[dict[str, str]] = {
        "externalid": "externalId",
        "companyname": "companyName",
        "phone": "phone",
        "fax": "fax",
        "url": "url",
        "comments": "comments",
    }
    references: ClassVar[dict[str, str]] = {"subsidiary": "subsidiary"}
    required_on_create: ClassVar[list[str]] = ["companyname"]

    @property
    def pii_safe_keys(self) -> list[str]:
        """Log-safe PII used to identify a customer."""
        return ["id", "externalid"]


class NetSuiteContactSink(NetSuiteRecordSink):

    record_path = "contact"
    record_label = "Contact"
    fields: ClassVar[dict[str, str]] = {
        "externalid": "externalId",
        "firstname": "firstName",
        "lastname": "lastName",
        "salutation": "salutation",
        "title": "title",
        "email": "email",
        "phone": "phone",
        "mobilephone": "mobilePhone",
        "fax": "fax",
    }
    references: ClassVar[dict[str, str]] = {"company": "company"}
    required_on_create: ClassVar[list[str]] = ["lastname"]

    @property
    def pii_safe_keys(self) -> list[str]:
        """Log-safe PII used to identify a contact."""
        return ["id", "externalid"]


class NetSuiteSalesOrderSink(NetSuiteRecordSink):

    # NetSuite's REST record name is camelCase, though the dbt stream is `salesorder`.
    record_path = "salesOrder"
    record_label = "Sales Order"
    fields: ClassVar[dict[str, str]] = {
        "externalid": "externalId",
        "trandate": "tranDate",
        "memo": "memo",
    }
    references: ClassVar[dict[str, str]] = {"entity": "entity"}
    sublists: ClassVar[dict[str, str]] = {"item": "item"}
    required_on_create: ClassVar[list[str]] = ["entity", "item"]

    @property
    def pii_safe_keys(self) -> list[str]:
        """Log-safe PII used to identify a sales order."""
        return ["id", "externalid"]


class NetSuiteInvoiceSink(NetSuiteRecordSink):

    record_path = "invoice"
    record_label = "Invoice"
    fields: ClassVar[dict[str, str]] = {
        "externalid": "externalId",
        "trandate": "tranDate",
        "memo": "memo",
    }
    references: ClassVar[dict[str, str]] = {
        "entity": "entity",
        "createdfrom": "createdFrom",
    }
    required_on_create: ClassVar[list[str]] = ["entity"]

    @property
    def pii_safe_keys(self) -> list[str]:
        """Log-safe PII used to identify an invoice."""
        return ["id", "externalid"]
