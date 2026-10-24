"""REST Stream type classes for tap-netsuite."""

from __future__ import annotations

import sys
import typing as t

from singer_sdk.pagination import BaseAPIPaginator
import xmltodict

from tap_netsuite.soap_client import NetSuiteSOAPStream

if sys.version_info >= (3, 9):
    import importlib.resources as importlib_resources
else:
    import importlib_resources

if t.TYPE_CHECKING:
    import requests

SCHEMAS_DIR = importlib_resources.files(__package__) / "schemas"


class ListFileCabinetStream(NetSuiteSOAPStream):
    """List of files in the file cabinet (in the configured folders)."""

    name = "file_cabinet_list"
    primary_keys: t.ClassVar[list[str]] = ["@internalId"]
    replication_key = None
    schema_filepath = SCHEMAS_DIR / f"{name}.json"

    @property
    def soap_action(self) -> str:
        return "search"

    def generate_soap_search_value(self, folder_id):
        return (
            f'<searchValue xmlns="urn:core_{self.WSDL_MAJOR_VERSION}.platform.webservices.netsuite.com">'  # noqa: E501
            f'<internalId xmlns="urn:core_{self.WSDL_MAJOR_VERSION}.platform.webservices.netsuite.com">{folder_id}</internalId>'  # noqa: E501
            f"</searchValue>"
        )

    def soap_body(
        self, context: dict, next_page_token: t.Any | None  # noqa: ARG002
    ) -> str:
        """
        Docs:
        1. Human readable: https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_N3516862.html
        2. XSD Schema: https://webservices.netsuite.com/xsd/documents/v2024_1_0/fileCabinet.xsd
        """
        return (
            f'<search xmlns="urn:messages_{self.WSDL_MAJOR_VERSION}.platform.webservices.netsuite.com">'  # noqa: E501
            f'<searchRecord xmlns="urn:filecabinet_{self.WSDL_MAJOR_VERSION}.documents.webservices.netsuite.com" xsi:type="FileSearchAdvanced">'  # noqa: E501
            f'<criteria xmlns="urn:filecabinet_{self.WSDL_MAJOR_VERSION}.documents.webservices.netsuite.com">'  # noqa: E501
            f'<basic xmlns="urn:filecabinet_{self.WSDL_MAJOR_VERSION}.documents.webservices.netsuite.com">'  # noqa: E501
            f'<folder xmlns="urn:common_{self.WSDL_MAJOR_VERSION}.platform.webservices.netsuite.com" operator="anyOf">'  # noqa: E501
            f"{''.join(self.generate_soap_search_value(folder_id) for folder_id in self.config['file_cabinet_folder_ids'])}"
            f"</folder>"
            f"</basic>"
            f"</criteria>"
            f"</searchRecord>"
            f"</search>"
        )

    def parse_response(self, response: requests.Response) -> t.Iterable[dict]:
        """
        Docs:
        1. XSD Schema:https://webservices.netsuite.com/xsd/documents/v2024_1_0/fileCabinet.xsd
        2. Example Response: README#example-responses

        Docs for pagination:
        1. Docs: https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_N3523074.html
        """
        response_dict = xmltodict.parse(response.content)
        envelope = response_dict.get("soapenv:Envelope", {})
        body = envelope.get("soapenv:Body", {})
        search_response = body.get("searchResponse", {})
        search_result = search_response.get("platformCore:searchResult", {})
        status = search_result.get("platformCore:status", {})
        is_success = status.get("@isSuccess")

        if is_success != "true":
            status_detail = status.get("platformCore:statusDetail", {})
            status_detail_type = status_detail.get("@type")
            status_detail_code = status_detail.get("platformCore:code")
            status_detail_message = status_detail.get("platformCore:message")
            error_msg = (
                f"Failed to execute SOAP query. {is_success=}, {status_detail_type=}, "
                f"{status_detail_code=}, {status_detail_message=}."
            )
            raise RuntimeError(error_msg)

        total_pages = search_result.get("platformCore:totalPages")
        if int(total_pages) > 1:
            error_msg = (
                "Pagination has not been implemented and we detected "
                "platformCore:totalPages > 1"
            )
            raise NotImplementedError(error_msg)

        # Not actually a list of records, we have to use platformCore:record
        record_list = search_result.get("platformCore:recordList")

        # If the response contains no records, platformCore:recordList is None
        # If the response contains only a single record, platformCore:record is a dict.
        # If the response contains multiple records, platformCore:record is a list.
        if record_list is None:
            return []
        record = record_list.get("platformCore:record", [])
        if isinstance(record, list):
            return record
        return [record]

    def get_child_context(
        self,
        record: dict,
        context: dict | None,  # noqa: ARG002
    ) -> dict:
        """Return a context dictionary for child streams."""
        return {
            "_sdc_file_id": record["@internalId"],
        }


class FileCabinetStream(NetSuiteSOAPStream):
    """Details on files."""

    name = "file_cabinet"
    primary_keys: t.ClassVar[list[str]] = ["@internalId"]
    replication_key = None
    schema_filepath = SCHEMAS_DIR / f"{name}.json"
    parent_stream_type = ListFileCabinetStream

    @property
    def soap_action(self) -> str:
        return "get"

    def soap_body(
        self, context: dict, next_page_token: t.Any | None  # noqa: ARG002
    ) -> str:
        """
        Docs: https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_N3488543.html#bridgehead_N3488555
        """
        return (
            f'<get xmlns="urn:messages_{self.WSDL_MAJOR_VERSION}.platform.webservices.netsuite.com" xsi:type="GetRequest">'  # noqa: E501
            f'<baseRef xmlns="urn:core_{self.WSDL_MAJOR_VERSION}.platform.webservices.netsuite.com" internalId="{context["_sdc_file_id"]}" type="file" xsi:type="RecordRef"/>'  # noqa: E501
            f"</get>"
        )

    def parse_response(self, response: requests.Response) -> t.Iterable[dict]:
        """
        Docs:
        1. Human readablehttps://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_N3488543.html#bridgehead_3705192937
        2. XSD Schema: https://webservices.netsuite.com/xsd/documents/v2024_1_0/fileCabinet.xsd
        3. Example Response: README#example-responses
        """
        response_dict = xmltodict.parse(response.content)
        envelope = response_dict.get("soapenv:Envelope", {})
        body = envelope.get("soapenv:Body", {})
        get_response = body.get("getResponse", {})
        read_response = get_response.get("readResponse", {})
        status = read_response.get("platformCore:status", {})
        is_success = status.get("@isSuccess")

        if is_success != "true":
            status_detail = status.get("platformCore:statusDetail", {})
            status_detail_type = status_detail.get("@type")
            status_detail_code = status_detail.get("platformCore:code")
            status_detail_message = status_detail.get("platformCore:message")
            error_msg = (
                f"Failed to execute SOAP query. {is_success=}, {status_detail_type=}, "
                f"{status_detail_code=}, {status_detail_message=}."
            )
            raise RuntimeError(error_msg)

        record = read_response["record"]
        return [record]


class SOAPSearchPaginator(BaseAPIPaginator):

    def __init__(self, *args, **kwargs):
        super().__init__(start_value=None, *args, **kwargs)\

    def has_more(self, response: requests.Response) -> bool:
        response_dict = xmltodict.parse(response.content)
        envelope = response_dict.get("soapenv:Envelope", {})
        body = envelope.get("soapenv:Body", {})
        search_response = body.get("searchResponse", {})
        search_result = search_response.get("platformCore:searchResult", {})
        page_index = search_result.get("platformCore:pageIndex", 0)
        total_pages = search_result.get("platformCore:totalPages", 0)
        return int(page_index) < int(total_pages)

    def get_next(self, response: requests.Response) -> t.Any | None:
        response_dict = xmltodict.parse(response.content)
        envelope = response_dict.get("soapenv:Envelope", {})
        header = envelope.get("soapenv:Header", {})
        document_info = header.get("platformMsgs:documentInfo", {})
        search_id = document_info.get("platformMsgs:nsId", None)
        body = envelope.get("soapenv:Body", {})
        search_response = body.get("searchResponse", {})
        search_result = search_response.get("platformCore:searchResult", {})
        page_index = search_result.get("platformCore:pageIndex", 0)
        return {"search_id": search_id, "page_index": int(page_index) + 1}


class TransactionStream(NetSuiteSOAPStream):
    """List of transactions."""

    name = "transaction"
    primary_keys: t.ClassVar[list[str]] = ["_sdc_internal_id"]
    replication_key = None
    schema_filepath = SCHEMAS_DIR / f"{name}.json"

    @property
    def soap_action(self) -> str:
        """Handled by headers_from_next_page_token."""
        return None

    def get_new_paginator(self) -> BaseAPIPaginator:
        return SOAPSearchPaginator()

    def headers_from_next_page_token(self, next_page_token: t.Any | None) -> dict:
        headers = super().http_headers
        if next_page_token is not None:
            headers["SOAPAction"] = "searchMoreWithId"
        else:
            headers["SOAPAction"] = "search"
        return headers

    @property
    def soap_basic_columns(self) -> list[str]:
        """List of columns to return from the transaction itself."""
        return ["internalId"]

    @property
    def soap_file_join_columns(self) -> list[str]:
        """List of columns to return form the transaction's associated file."""
        return ["internalId"]

    def soap_basic(self) -> str:
        """SOAP object representing the transaction's columns."""
        return ''.join(f'<{column} xmlns="urn:common_{self.WSDL_MAJOR_VERSION}.platform.webservices.netsuite.com"/>' for column in self.soap_basic_columns)

    def soap_file_join(self) -> str:
        """SOAP object representing the transaction's associated file's columns."""
        return ''.join(f'<{column} xmlns="urn:common_{self.WSDL_MAJOR_VERSION}.platform.webservices.netsuite.com"/>' for column in self.soap_file_join_columns)

    def soap_body(
        self, context: dict, next_page_token: t.Any | None  # noqa: ARG002
    ) -> str:
        if next_page_token is None:
            return (
                f'<search xmlns="urn:messages_{self.WSDL_MAJOR_VERSION}.platform.webservices.netsuite.com">'
                f'<searchRecord xmlns:tranSales="urn:sales_{self.WSDL_MAJOR_VERSION}.transactions.webservices.netsuite.com" xsi:type="tranSales:TransactionSearchAdvanced">'
                f'<tranSales:columns>'
                f'<tranSales:basic>'
                f'{self.soap_basic()}'
                f'</tranSales:basic>'
                f'<tranSales:fileJoin>'
                f'{self.soap_file_join()}'
                f'</tranSales:fileJoin>'
                f'</tranSales:columns>'
                f'</searchRecord>'
                f'</search>'
            )
        else:
            return (
                f'<searchMoreWithId xmlns="urn:messages_{self.WSDL_MAJOR_VERSION}.platform.webservices.netsuite.com">'  # noqa: E501
                f'<searchId>{next_page_token["search_id"]}</searchId>'
                f'<pageIndex>{next_page_token["page_index"]}</pageIndex>'
                f'</searchMoreWithId>'
            )

    def parse_response(self, response: requests.Response) -> t.Iterable[dict]:
        response_dict = xmltodict.parse(response.content)
        envelope = response_dict.get("soapenv:Envelope", {})
        body = envelope.get("soapenv:Body", {})
        search_response = body.get("searchMoreWithIdResponse", body.get("searchResponse", {}))
        search_result = search_response.get("platformCore:searchResult", {})
        status = search_result.get("platformCore:status", {})
        is_success = status.get("@isSuccess")

        if is_success != "true":
            status_detail = status.get("platformCore:statusDetail", {})
            status_detail_type = status_detail.get("@type")
            status_detail_code = status_detail.get("platformCore:code")
            status_detail_message = status_detail.get("platformCore:message")
            error_msg = (
                f"Failed to execute SOAP query. {is_success=}, {status_detail_type=}, "
                f"{status_detail_code=}, {status_detail_message=}."
            )
            raise RuntimeError(error_msg)

        # Not actually a list of records, we have to use platformCore:record
        record_list = search_result.get("platformCore:searchRowList")

        # If the response contains no records, platformCore:recordList is None
        # If the response contains only a single record, platformCore:record is a dict.
        # If the response contains multiple records, platformCore:record is a list.
        if record_list is None:
            return []
        record = record_list.get("platformCore:searchRow", [])
        if isinstance(record, list):
            return record
        return [record]

    def post_process(self, row: dict, context: dict | None) -> dict:
        row["_sdc_internal_id"] = row["tranSales:basic"]["platformCommon:internalId"]["platformCore:searchValue"]["@internalId"]
        return row

    def prepare_request(
        self,
        context: dict | None,
        next_page_token: t.Any | None,
    ) -> requests.PreparedRequest:
        """Override to calculate headers based on next_page_token."""

        http_method = self.rest_method
        url: str = self.get_url(context)
        params: dict | str = self.get_url_params(context, next_page_token)
        request_data = self.prepare_request_payload(context, next_page_token)
        headers = self.headers_from_next_page_token(next_page_token)

        return self.build_prepared_request(
            method=http_method,
            url=url,
            params=params,
            headers=headers,
            data=request_data,
        )
