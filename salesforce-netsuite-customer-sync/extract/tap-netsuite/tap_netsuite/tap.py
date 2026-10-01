"""NetSuite tap class."""

from __future__ import annotations

from singer_sdk import Tap
from singer_sdk import typing as th  # JSON schema typing helpers

from tap_netsuite import rest_streams, soap_streams


class TapNetSuite(Tap):
    """NetSuite tap class."""

    name = "tap-netsuite"

    config_jsonschema = th.PropertiesList(
        th.Property(
            "production",
            th.BooleanType,
            required=True,
            default=False,
            description=(
                "If set to false, will fail if a Production account ID is used. If set "
                "to true, will fail if a Sandbox or Release Preview account ID is used."
            ),
        ),
        th.Property(
            "account_id",
            th.StringType,
            required=True,
            description=(
                "Your NetSuite instance's account ID. For production accounts, this "
                "can be found at the beginning of your NetSuite URL. For example, if "
                "your URL is `https://1234567.app.netsuite.com`, your account ID is "
                "`1234567`. For Sandbox and Release Preview accounts, refer to the "
                "[docs](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_1498754928.html)."
            ),
        ),
        th.Property(
            "client_id",
            th.StringType,
            required=True,
            secret=True,
            description=(
                "Your NetSuite client ID, obtained when you set up OAuth 2.0. For more "
                "information, check the [docs](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_157771733782.html). "  # noqa: E501
                "Note that both your client ID and client secret are sensitive . From "
                "the [docs](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_157771733782.html): "  # noqa: E501
                '"If you lose or forget the client ID and client secret, you will have '
                "to reset them on the Integration page, to obtain new values. Treat "
                "these values as you would a password."
            ),
        ),
        th.Property(
            "certificate_id",
            th.StringType,
            required=True,
            description=(
                "Your certificate ID, displayed when setting up your private key. You "
                "can learn more about certificates from the [docs](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_162686838198.html)."
            ),
        ),
        th.Property(
            "private_key",
            th.StringType,
            required=True,
            secret=True,
            description=(
                "A certificate representing a private key, used for JWT Auth. You may "
                "provide this value either as a file path or directly as a certificate."
                "You can learn more about certificates from the [docs](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_162686838198.html)."
            ),
        ),
        th.Property(
            "timesheet_query_mode",
            th.StringType,
            required=True,
            default="all",
            allowed_values=["all", "since_last_saturday", "two_weeks_ago"],
            description=(
                "Determines the query used to fetch timesheets. `all` will fetch every "
                "timesheet available. `since_last_saturday` will fetch only those with "
                "a start date on or after last Saturday."
            ),
        ),
        th.Property(
            "employee_fields",
            th.StringType,
            required=True,
            default="all",
            description=(
                "Comma-separated list of employee fields to fetch. This is opt-in "
                "because of the potential for sensitive information (such as SSN) to "
                "be present."
            ),
        ),
        th.Property(
            "soap_consumer_key",
            th.StringType,
            required=False,
            secret=True,
            description=(
                "CONSUMER KEY from setting up SOAP Token-Based Authentication."
            ),
        ),
        th.Property(
            "soap_consumer_secret",
            th.StringType,
            required=False,
            secret=True,
            description=(
                "CONSUMER SECRET from setting up SOAP Token-Based Authentication."
            ),
        ),
        th.Property(
            "soap_token_id",
            th.StringType,
            required=False,
            secret=True,
            description=("TOKEN ID from setting up SOAP Token-Based Authentication."),
        ),
        th.Property(
            "soap_token_secret",
            th.StringType,
            required=False,
            secret=True,
            description=(
                "TOKEN SECRET from setting up SOAP Token-Based Authentication."
            ),
        ),
        th.Property(
            "file_cabinet_folder_ids",
            th.ArrayType(th.StringType),
            required=False,
            description=(
                "List of folder internal IDs. Only files contained within the "
                "specified folders will be synced. Both direct children and files in "
                "subfolders will be synced. For information on how to find folder "
                "internal IDs, see below in the [README](#file-cabinet-folder-ids)."
            ),
        ),
    ).to_dict()

    def _validate_config(self, *, raise_errors: bool = True) -> list[str]:
        errors_list = super()._validate_config(raise_errors=raise_errors)
        production: bool = self.config["production"]
        account_id: str = self.config["account_id"]
        if production and not account_id.isdigit():
            error_msg = (
                "`production` is set to True but `account_id` is from a Sandbox or "
                "Release Preview account."
            )
            errors_list.append(error_msg)
            if raise_errors:
                raise ValueError(error_msg)
        if not production and account_id.isdigit():
            error_msg = (
                "`production` is set to False but `account_id` is from a Production "
                "account."
            )
            errors_list.append(error_msg)
            if raise_errors:
                raise ValueError(error_msg)
        return errors_list

    def discover_streams(self) -> list[rest_streams.NetSuiteRESTStream]:
        """Return a list of discovered streams.

        Returns:
            A list of discovered streams.
        """
        streams = [
            rest_streams.TimeSheetListStream(self),
            rest_streams.TimeSheetStream(self),
            rest_streams.TimeBillListStream(self),
            rest_streams.TimeBillStream(self),
            rest_streams.EmployeeListStream(self),
            rest_streams.EmployeeStream(self),
            rest_streams.LocationListStream(self),
            rest_streams.LocationStream(self),
            rest_streams.CustomerStream(self),
            rest_streams.ContactStream(self),
            soap_streams.TransactionStream(self),
        ]
        if self.config.get("file_cabinet_folder_ids"):
            streams.extend([
                soap_streams.ListFileCabinetStream(self),
                soap_streams.FileCabinetStream(self),
            ])
        return streams
