"""REST Stream type classes for tap-netsuite."""

from __future__ import annotations

import datetime
import sys
import typing as t

from tap_netsuite.rest_client import (
    NetSuiteListRESTStream,
    NetSuiteRESTStream,
    NetSuiteSuiteQLStream,
)

if sys.version_info >= (3, 9):
    import importlib.resources as importlib_resources
else:
    import importlib_resources

SCHEMAS_DIR = importlib_resources.files(__package__) / "schemas"


class TimeSheetListStream(NetSuiteListRESTStream):
    """List of all timesheets."""

    name = "timesheet_list"
    path = "/record/v1/timesheet"
    primary_keys: t.ClassVar[list[str]] = ["id"]
    replication_key = None
    schema_filepath = SCHEMAS_DIR / f"{name}.json"

    def get_url_params(
        self, context: t.Any | None, next_page_token: t.Any | None
    ) -> dict[str, t.Any]:
        params: dict = super().get_url_params(context, next_page_token)
        params["q"] = self.build_timesheet_query()
        return params

    def build_timesheet_query(self) -> str:
        timesheet_query_mode = self.config["timesheet_query_mode"]
        if timesheet_query_mode == "all":
            return ""
        if timesheet_query_mode == "since_last_saturday":
            # This could be condensed into a one-liner but that would be unreadable.
            saturday = 5
            days_in_a_week = 7
            today = datetime.datetime.now(tz=datetime.timezone.utc).date()
            offset = (today.weekday() - saturday) % days_in_a_week
            if offset == 0:  # Today is Saturday, use previous Saturday for last 7 days
                offset = 7
            last_saturday = today - datetime.timedelta(days=offset)
            last_saturday_string = last_saturday.strftime("%m/%d/%Y")
            return f'startDate ON_OR_AFTER "{last_saturday_string}"'
        if timesheet_query_mode == "two_weeks_ago": # I know we could do better here but this was quick
            today = datetime.datetime.now(tz=datetime.timezone.utc).date()
            two_weeks_ago = today - datetime.timedelta(days=14)
            two_weeks_ago_string = two_weeks_ago.strftime("%m/%d/%Y")
            return f'startDate ON_OR_AFTER "{two_weeks_ago_string}"'

        # Should never happen because meltano validates config.
        error_msg = f"Invalid `timesheet_query_mode` of {timesheet_query_mode}."
        raise RuntimeError(error_msg)

    def get_child_context(
        self,
        record: dict,
        context: dict | None,  # noqa: ARG002
    ) -> dict:
        """Return a context dictionary for child streams."""
        return {
            "_sdc_timesheet_id": record["id"],
        }


class TimeSheetStream(NetSuiteRESTStream):
    """Details on timesheets."""

    name = "timesheet"
    path = "/record/v1/timesheet/{_sdc_timesheet_id}"
    primary_keys: t.ClassVar[list[str]] = ["id"]
    replication_key = None
    schema_filepath = SCHEMAS_DIR / f"{name}.json"
    parent_stream_type = TimeSheetListStream


class TimeBillListStream(NetSuiteListRESTStream):
    """List of all time bills for a given timesheet."""

    name = "timebill_list"
    path = "/record/v1/timebill"
    primary_keys: t.ClassVar[list[str]] = ["id"]
    replication_key = None
    schema_filepath = SCHEMAS_DIR / f"{name}.json"
    parent_stream_type = TimeSheetListStream

    def get_url_params(
        self, context: t.Any | None, next_page_token: t.Any | None
    ) -> dict[str, t.Any]:
        params: dict = super().get_url_params(context, next_page_token)
        params["q"] = f"timesheet EQUAL {context['_sdc_timesheet_id']}"
        return params

    def get_child_context(
        self,
        record: dict,
        context: dict | None,  # noqa: ARG002
    ) -> dict:
        """Return a context dictionary for child streams."""
        return {
            "_sdc_timebill_id": record["id"],
        }


class TimeBillStream(NetSuiteRESTStream):
    """Details on time bills."""

    name = "timebill"
    path = "/record/v1/timebill/{_sdc_timebill_id}"
    primary_keys: t.ClassVar[list[str]] = ["id"]
    replication_key = None
    schema_filepath = SCHEMAS_DIR / f"{name}.json"
    parent_stream_type = TimeBillListStream


class EmployeeListStream(NetSuiteListRESTStream):
    """List of all employees."""

    name = "employee_list"
    path = "/record/v1/employee"
    primary_keys: t.ClassVar[list[str]] = ["id"]
    replication_key = None
    schema_filepath = SCHEMAS_DIR / f"{name}.json"

    def get_child_context(
        self,
        record: dict,
        context: dict | None,  # noqa: ARG002
    ) -> dict:
        """Return a context dictionary for child streams."""
        return {
            "_sdc_employee_id": record["id"],
        }


class EmployeeStream(NetSuiteRESTStream):
    """Details on employees."""

    name = "employee"
    path = "/record/v1/employee/{_sdc_employee_id}"
    primary_keys: t.ClassVar[list[str]] = ["id"]
    replication_key = None
    schema_filepath = SCHEMAS_DIR / f"{name}.json"
    parent_stream_type = EmployeeListStream

    def get_url_params(
        self, context: t.Any | None, next_page_token: t.Any | None
    ) -> dict[str, t.Any]:
        params: dict = super().get_url_params(context, next_page_token)
        params["fields"] = self.config["employee_fields"]
        return params


class LocationListStream(NetSuiteListRESTStream):
    "List of all locations."

    name = "location_list"
    path = "/record/v1/location"
    primary_keys: t.ClassVar[list[str]] = ["id"]
    replication_key = None
    schema_filepath = SCHEMAS_DIR / f"{name}.json"

    def get_child_context(
        self,
        record: dict,
        context: dict | None,  # noqa: ARG002
    ) -> dict:
        """Return a context dictionary for child streams."""
        return {
            "_sdc_location_id": record["id"],
        }


class LocationStream(NetSuiteRESTStream):
    """Details on locations."""

    name = "location"
    path = "/record/v1/location/{_sdc_location_id}"
    primary_keys: t.ClassVar[list[str]] = ["id"]
    replication_key = None
    schema_filepath = SCHEMAS_DIR / f"{name}.json"
    parent_stream_type = LocationListStream


class CustomerStream(NetSuiteSuiteQLStream):
    """Details on customers."""

    name = "customer"
    table = "customer"
    primary_keys: t.ClassVar[list[str]] = ["id"]
    replication_key = None
    schema_filepath = SCHEMAS_DIR / f"{name}.json"


class ContactStream(NetSuiteSuiteQLStream):
    """Details on contacts."""

    name = "contact"
    table = "contact"
    primary_keys: t.ClassVar[list[str]] = ["id"]
    replication_key = None
    schema_filepath = SCHEMAS_DIR / f"{name}.json"
