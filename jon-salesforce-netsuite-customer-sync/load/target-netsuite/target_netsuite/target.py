"""NetSuite target class."""

from __future__ import annotations

from typing import TYPE_CHECKING

from singer_sdk import typing as th
from singer_sdk.target_base import Target

from target_netsuite.sinks import (
    NetSuiteContactSink,
    NetSuiteCustomerSink,
    NetSuiteInvoiceSink,
    NetSuiteSalesOrderSink,
    NetSuiteTimeBillSink,
    NetSuiteTimeSheetSink,
)

if TYPE_CHECKING:
    from singer_sdk.sinks import Sink


class TargetNetSuite(Target):
    """Sample target for NetSuite."""

    name = "target-netsuite"

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
            "api_timeout",
            th.IntegerType,
            required=True,
            description="Timeout in seconds when accessing the API",
            default=90,
        ),
        th.Property(
            "max_errors",
            th.IntegerType,
            required=True,
            description=(
                "Maximum number individual record failures before failing the "
                "entire target. Set to -1 to allow any number of failures."
            ),
            default=10,
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

    def get_sink_class(self, stream_name: str) -> Sink:
        if "timesheet" in stream_name.lower():
            return NetSuiteTimeSheetSink
        if "timebill" in stream_name.lower():
            return NetSuiteTimeBillSink
        if "salesorder" in stream_name.lower():
            return NetSuiteSalesOrderSink
        if "customer" in stream_name.lower():
            return NetSuiteCustomerSink
        if "contact" in stream_name.lower():
            return NetSuiteContactSink
        if "invoice" in stream_name.lower():
            return NetSuiteInvoiceSink
        error_msg = f"Could not determine sink from a stream name of '{stream_name}'."
        raise ValueError(error_msg)


if __name__ == "__main__":
    TargetNetSuite.cli()
