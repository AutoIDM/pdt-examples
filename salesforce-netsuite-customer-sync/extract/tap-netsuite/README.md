# tap-netsuite

`tap-netsuite` is a Singer tap for NetSuite.

## Configuration

### Accepted Config Options

| Setting | Required | Default | Description |
|:--------|:--------:|:-------:|:------------|
| production | True     |       0 | If set to false, will fail if a Production account ID is used. If set to true, will fail if a Sandbox or Release Preview account ID is used. |
| account_id | True     | None    | Your NetSuite instance's account ID. For production accounts, this can be found at the beginning of your NetSuite URL. For example, if your URL is `https://1234567.app.netsuite.com`, your account ID is `1234567`. For Sandbox and Release Preview accounts, refer to the [docs](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_1498754928.html). |
| client_id | True     | None    | Your NetSuite client ID, obtained when you set up OAuth 2.0. For more information, check the [docs](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_157771733782.html). Note that both your client ID and client secret are sensitive . From the [docs](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_157771733782.html): "If you lose or forget the client ID and client secret, you will have to reset them on the Integration page, to obtain new values. Treat these values as you would a password. |
| certificate_id | True     | None    | Your certificate ID, displayed when setting up your private key. You can learn more about certificates from the [docs](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_162686838198.html). |
| private_key | True     | None    | A certificate representing a private key, used for JWT Auth. You may provide this value either as a file path or directly as a certificate.You can learn more about certificates from the [docs](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_162686838198.html). |
| timesheet_query_mode | True     | all     | Determines the query used to fetch timesheets. `all` will fetch every timesheet available. `since_last_saturday` will fetch only those with a start date on or after last Saturday. |
| employee_fields | True     | all     | Comma-separated list of employee fields to fetch. This is opt-in because of the potential for sensitive information (such as SSN) to be present. |
| soap_consumer_key | True     | None    | CONSUMER KEY from setting up SOAP Token-Based Authentication. |
| soap_consumer_secret | True     | None    | CONSUMER SECRET from setting up SOAP Token-Based Authentication. |
| soap_token_id | True     | None    | TOKEN ID from setting up SOAP Token-Based Authentication. |
| soap_token_secret | True     | None    | TOKEN SECRET from setting up SOAP Token-Based Authentication. |
| file_cabinet_folder_ids | False    | None    | List of folder internal IDs. Only files contained within the specified folders will be synced. Both direct children and files in subfolders will be synced. For information on how to find folder internal IDs, see below in the [README](#file-cabinet-folder-ids). |
| stream_maps | False    | None    | Config object for stream maps capability. For more information check out [Stream Maps](https://sdk.meltano.com/en/latest/stream_maps.html). |
| stream_map_config | False    | None    | User-defined config values to be used within map expressions. |
| faker_config | False    | None    | Config for the [`Faker`](https://faker.readthedocs.io/en/master/) instance variable `fake` used within map expressions. Only applicable if the plugin specifies `faker` as an addtional dependency (through the `singer-sdk` `faker` extra or directly). |
| faker_config.seed | False    | None    | Value to seed the Faker generator for deterministic output: https://faker.readthedocs.io/en/master/#seeding-the-generator |
| faker_config.locale | False    | None    | One or more LCID locale strings to produce localized output for: https://faker.readthedocs.io/en/master/#localization |
| flattening_enabled | False    | None    | 'True' to enable schema flattening and automatically expand nested properties. |
| flattening_max_depth | False    | None    | The max depth to flatten schemas. |
| batch_config | False    | None    |             |
| batch_config.encoding | False    | None    | Specifies the format and compression of the batch files. |
| batch_config.encoding.format | False    | None    | Format to use for batch files. |
| batch_config.encoding.compression | False    | None    | Compression format to use for batch files. |
| batch_config.storage | False    | None    | Defines the storage layer to use when writing batch files |
| batch_config.storage.root | False    | None    | Root path to use when writing batch files. |
| batch_config.storage.prefix | False    | None    | Prefix to use when writing batch files. |

A full list of supported settings and capabilities for this
tap is available by running:

```bash
tap-netsuite --about
```

### Configure using environment variables

This Singer tap will automatically import any environment variables within the working directory's
`.env` if the `--config=ENV` is provided, such that config values will be considered if a matching
environment variable is set either in the terminal context or in the `.env` file.

### Source Authentication and Authorization

#### Authenticate with REST Web Services

AutoIDM Steps:
1. Generate a certificate and private key by running the below bash commmand, replacing `CUSTOMERNAME` with the name of the client you are working with.
    ```bash
    openssl req -new -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes -days 730 -out CUSTOMERNAME_netsuite_certificate.pem -keyout CUSTOMERNAME_netsuite_private_key.pem -subj "/C=US/ST=Michigan/L=Kalamazoo/O=AutoIDM/OU=autoidm.com/CN=autoidm.com/emailAddress=info@autoidm.com"
    ```
2. Send the `CUSTOMERNAME_netsuite_certificate.pem` file to the client, along with the below access instructions.
3. After receiving the client's Account ID, Client ID, and Certificate ID, put them into the tap's config, along with the path to the `CUSTOMERNAME_netsuite_private_key.pem` file.

Client Steps:
1. Provide AutoIDM with your Account ID. This can be found in your NetSuite URL. For example, if your URL is `https://1234567.app.netsuite.com`, your account ID is `1234567`.
2. Enable REST web services and OAuth 2.0.
    1. From the top menu bar, select `Setup > Company > Enable Features`.
    2. Select the `SuiteCloud` subtab.
    3. Find the `SuiteTalk (Web Services)` section and check the `REST` checkbox.
    4. Find the `SuiteScript` section and check both the `CLIENT SUITESCRIPT` and `SERVER SUITESCRIPT` checkboxes.
    5. Find the `Manage Authentication` section and check the `OAUTH 2.0` checkbox. 
3. Set up OAuth2.0 Client Credentials.
    1. Note the ID of any NetSuite account with the role of Administrator.
    2. From the top menu bar, select `Setup > Integrations > Manage Integrations > New`.
    3. Enter a descriptive title in the `Name` field, such as "AutoIDM OAuth2.0 Key". Note this value for later.
    4. Ensure that the `State` dropdown is set to "Enabled".
    5. Select the `Authentication` subtab if you aren't already on it.
    6. In the `Token-based Authentication` section, uncheck the `TOKEN-BASED AUTHENTICATION` checkbox.
    7. In the `OAuth 2.0` section:
        1. Uncheck the `AUTHORIZATION GRANT` and `PUBLIC CLIENT` checkboxes.
        2. Check the `CLIENT CREDENTIALS (MACHINE TO MACHINE) GRANT` checkbox.
        3. Check the `REST WEB SERVICES` checkbox.
    8. In the `User Credentials` section, uncheck the `USER CREDENTIALS` checkbox.
    9. Press `Save`.
    10. Two values will be displayed, a `CONSUMER KEY / CLIENT ID` value and a `CONSUMER SECRET / CLIENT SECRET` value. Send the `CONSUMER KEY / CLIENT ID` value to AutoIDM securely (such as through https://onetimesecret.com/).
    11. From the top menu bar, select `Setup > Integration > OAuth 2.0 Client Credentials (M2M) Setup`.
    12. Select the `Create New` button, bringing up the `Create a New Client Credentials Mapping` pop-up.
    13. In the `Entity` dropdown, enter the ID of an Administrator account you noted earlier.
    14. In the `Role` dropdown, select "Administrator".
    15. In the `Application` dropdown, enter the name of the OAuth2.0 Application you created earlier (such as "AutoIDM OAuth2.0 Key").
    16. In the `Certificate` box, click the `Choose a file` button, then upload the `.cer` file provided to you by AutoIDM.
    17. Click the `Save` button.
    18. A value will be displayed: `CERTIFICATE ID`. Note this value and send it to AutoIDM.

You can learn about NetSuite authentication from the [docs](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_1544787084.html)

#### Authenticate with SOAP Web Services

Client Steps:
1. Enable SOAP web services and Token-Based Authentication (TBA).
    1. From the top menu bar, select `Setup > Company > Enable Features`.
    2. Select the `SuiteCloud` subtab.
    3. Find the `SuiteTalk (Web Services)` section and check the `SOAP` checkbox.
    4. Find the `SuiteScript` section and check both the `CLIENT SUITESCRIPT` and `SERVER SUITESCRIPT` checkboxes.
    5. Find the `Manage Authentication` section and check the `TOKEN-BASED AUTHENTICATION` checkbox.
    6. Press `Save`.
2. Create a new role for Token-Based Authentication authentication.
    1. From the top menu bar, select `Setup > Users/Roles > Manage Roles > New`.
    2. Enter a descriptive title in the `Name` field, such as "AutoIDM SOAP Token-Based Authentication Role".
    3. At the bottom of the page, select `Permissions > Lists` and add the roles: "Documents and Files" and "Perform Search".
    4. At the bottom of the page, select `Permissions > Setup` and add the roles: "Access Token Management", "Log in using Access Tokens", "SOAP Web Services", and "User Access Tokens".
    5. At the bottom of the page, select `Permissions > Transactions` and add the roles: "Find Transaction" and "Invoice".
    6. Press `Save`.
3. Assign the newly created role.
    1. From the top menu bar, select `Lists > Employees > Employees`.
    2. Choose an account the integration will use (or create a new one) and select `Edit`.
    3. At the bottom of the Page, select `Roles`.
    4. Add the role you created in step #2.
    5. Press `Save`.
4. Create an Integration Record
    1. From the top menu bar, select `Setup > Integration > Manage Integrations > New`.
    2. Enter a descriptive title in the `Name` field, such as "AutoIDM Integration Record".
    3. Ensure that the `State` dropdown is to "Enabled".
    4. Select the `Authentication` subtab if you aren't already on it.
    5. In the `Token-based Authentication` section:
        1. Check the `TOKEN-BASED AUTHENTICATION` checkbox.
        2. Uncheck the `TBA: ISSUETOKEN ENDPOINT` checkbox.
        3. Uncheck the `TBA: AUTHORIZATION FLOW` checkbox.
    6. In the `OAuth 2.0` section, uncheck the `AUTHORIZATION CODE GRANT` and `CLIENT CREDENTIALS (MACHINE TO MACHINE) GRANT` checkboxes.
    7. In the `User Credentials` section, uncheck the `USER CREDENTIALS` checkbox.
    8. Press `Save`.
    9. Two values will be displayed, a `CONSUMER KEY / CLIENT ID` value and a `CONSUMER SECRET / CLIENT SECRET` value. Send them both to AutoIDM securely (such as through https://onetimesecret.com/).
5. Create an Access Token
    1. From the top menu bar, select `Setup > Users/Roles > Access Tokens > New`.
    2. In the `APPLICATION NAME` dropdown, select the name of the Integration Record you created in step #4.
    3. In the `USER` dropdown, select the name of the employee you chose in step #3.
    4. In the `ROLE` dropdown, select the name of the role you created in step #2.
    5. A name will be automatically populated in the `NAME` field. Change it if you wish.
    6. Press `Save`.
    7. Two values will be displayed, a `TOKEN ID` value and a `TOKEN SECRET` value. Send them both to AutoIDM securely (such as through https://onetimesecret.com/).

## Usage

You can easily run `tap-netsuite` by itself or in a pipeline using [Meltano](https://meltano.com/).

### Executing the Tap Directly

```bash
tap-netsuite --version
tap-netsuite --help
tap-netsuite --config CONFIG --discover > ./catalog.json
```

## Developer Resources

Follow these instructions to contribute to this project.

### Initialize your Development Environment

```bash
pipx install poetry
poetry install
```

### Create and Run Tests

Create tests within the `tests` subfolder and
  then run:

```bash
poetry run pytest
```

You can also test the `tap-netsuite` CLI interface directly using `poetry run`:

```bash
poetry run tap-netsuite --help
```

### Testing with [Meltano](https://www.meltano.com)

_**Note:** This tap will work in any Singer environment and does not require Meltano.
Examples here are for convenience and to streamline end-to-end orchestration scenarios._

Next, install Meltano (if you haven't already) and any needed plugins:

```bash
# Install meltano
pipx install meltano
# Initialize meltano within this directory
cd tap-netsuite
meltano install
```

Now you can test and orchestrate using Meltano:

```bash
# Test invocation:
meltano invoke tap-netsuite --version
# OR run a test `elt` pipeline:
meltano elt tap-netsuite target-jsonl
```

## Generate a Token
Checkout ./scripts/generate_jwt_token.py and run it.

### SDK Dev Guide

See the [dev guide](https://sdk.meltano.com/en/latest/dev_guide.html) for more instructions on how to use the SDK to
develop your own taps and targets.

# SOAP Web Services

## Why use SOAP Web Services?

In general, we should default to using the REST API. Some streams, such as accessing the file cabinet, are not available through REST. In these cases, we use the SOAP API instead.

## Token-Based Authentication

Token-Based Authentication (sometimes referred to as "TBA") is the main method for authenticating with SOAP Web Services. 

For details on authenticating with SOAP Web services, read the [Authenticate with SOAP Web Services](#authenticate-with-soap-web-services) section.

For more information, read the [docs](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_N3445710.html#bridgehead_4489663579) on Token-Based Authentication.

## File Cabinet Folder IDs

One reason to use the SOAP API is to access the file cabinet. You'll need folder internal IDs for the `file_cabinet_folder_ids` setting. You can find these with the following steps:
1. Go to `https://{YOUR_ACCOUNT_ID}.app.netsuite.com/app/common/search/search.nl?searchtype=Folder`.
2. Press the `Submit` button.
3. Find the folder you wish to sync files from and press `View`.
4. Your URL will be something like: `https://{YOUR_ACCOUNT_ID}.app.netsuite.com/app/common/media/mediaitemfolder.nl?id={YOUR_FOLDER_ID}`. The ID you need is shown in your URL in place of `{YOUR_FOLDER_ID}`.

# Example Responses

## file_cabinet_list

Request:
```
POST /services/NetSuitePort_2023_2 HTTP/1.1
Content-Type: text/xml
SOAPAction: search
User-Agent: PostmanRuntime/7.41.2
Accept: */*
Host: {YOUR_ACCOUNT_ID}.suitetalk.api.netsuite.com
Accept-Encoding: gzip, deflate, br
Connection: keep-alive
Content-Length: 2038
 
<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns="http://www.w3.org/2001/XMLSchema">
<soapenv:Header>
<ns:tokenPassport xmlns:ns="urn:messages_2023_2.platform.webservices.netsuite.com">
<ns:account>{YOUR_ACCOUNT_ID}</ns:account>
<ns:consumerKey>{YOUR_CONSUMER_KEY}</ns:consumerKey>
<ns:token>{YOUR_TOKEN_ID}</ns:token>
<ns:nonce>alphabravo</ns:nonce>
<ns:timestamp>1726258146</ns:timestamp>
<ns:signature algorithm="HMAC_SHA256">{YOUR_SIGNATURE}</ns:signature>
</ns:tokenPassport>
</soapenv:Header>
<soapenv:Body>
<search xmlns="urn:messages_2023_2.platform.webservices.netsuite.com">
<searchRecord xmlns="urn:filecabinet_2023_2.documents.webservices.netsuite.com" xsi:type="FileSearchAdvanced">
<criteria xmlns="urn:filecabinet_2023_2.documents.webservices.netsuite.com">
<basic xmlns="urn:filecabinet_2023_2.documents.webservices.netsuite.com">
<folder xmlns="urn:common_2023_2.platform.webservices.netsuite.com" operator="anyOf">
<q2:searchValue xmlns:q2="urn:core_2023_2.platform.webservices.netsuite.com">
<internalId xmlns="urn:core_2023_2.platform.webservices.netsuite.com">5334</internalId>
</q2:searchValue>
</folder>
</basic>
</criteria>
</searchRecord>
</search>
</soapenv:Body>
</soapenv:Envelope>
```

Response:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <soapenv:Header>
        <platformMsgs:documentInfo xmlns:platformMsgs="urn:messages_2023_2.platform.webservices.netsuite.com">
            <platformMsgs:nsId>WEBSERVICES_{YOUR_ACCOUNT_ID}_091320243186865151865402262_d2d5c693</platformMsgs:nsId>
        </platformMsgs:documentInfo>
    </soapenv:Header>
    <soapenv:Body>
        <searchResponse xmlns="urn:messages_2023_2.platform.webservices.netsuite.com">
            <platformCore:searchResult xmlns:platformCore="urn:core_2023_2.platform.webservices.netsuite.com">
                <platformCore:status isSuccess="true"/>
                <platformCore:totalRecords>2</platformCore:totalRecords>
                <platformCore:pageSize>1000</platformCore:pageSize>
                <platformCore:totalPages>1</platformCore:totalPages>
                <platformCore:pageIndex>1</platformCore:pageIndex>
                <platformCore:searchId>WEBSERVICES_{YOUR_ACCOUNT_ID}_091320243186865151865402262_d2d5c693</platformCore:searchId>
                <platformCore:recordList>
                    <platformCore:record internalId="22519" xsi:type="docFileCab:File" xmlns:docFileCab="urn:filecabinet_2023_2.documents.webservices.netsuite.com">
                        <docFileCab:name>example_report.csv</docFileCab:name>
                        <docFileCab:mediaTypeName>CSV File</docFileCab:mediaTypeName>
                        <docFileCab:fileType>_CSV</docFileCab:fileType>
                        <docFileCab:folder internalId="5334">
                            <platformCore:name>Reports : Example Reports</platformCore:name>
                        </docFileCab:folder>
                        <docFileCab:fileSize>377.0</docFileCab:fileSize>
                        <docFileCab:url>https://{YOUR_ACCOUNT_ID}.app.netsuite.com/core/media/media.nl?id=22519&amp;c={YOUR_ACCOUNT_ID}&amp;h={FILE_HASH}&amp;_xt=.csv</docFileCab:url>
                        <docFileCab:textFileEncoding>_utf8</docFileCab:textFileEncoding>
                        <docFileCab:isOnline>false</docFileCab:isOnline>
                        <docFileCab:isInactive>false</docFileCab:isInactive>
                        <docFileCab:class>none</docFileCab:class>
                        <docFileCab:department>none</docFileCab:department>
                        <docFileCab:isPrivate>false</docFileCab:isPrivate>
                        <docFileCab:owner internalId="54576">
                            <platformCore:name>4306</platformCore:name>
                        </docFileCab:owner>
                        <docFileCab:lastModifiedDate>2024-09-11T11:30:38.000-07:00</docFileCab:lastModifiedDate>
                        <docFileCab:createdDate>2024-09-11T11:28:51.000-07:00</docFileCab:createdDate>
                    </platformCore:record>
                    <platformCore:record internalId="22619" xsi:type="docFileCab:File" xmlns:docFileCab="urn:filecabinet_2023_2.documents.webservices.netsuite.com">
                        <docFileCab:name>test2.csv</docFileCab:name>
                        <docFileCab:mediaTypeName>CSV File</docFileCab:mediaTypeName>
                        <docFileCab:fileType>_CSV</docFileCab:fileType>
                        <docFileCab:folder internalId="5334">
                            <platformCore:name>Reports : Example Reports</platformCore:name>
                        </docFileCab:folder>
                        <docFileCab:fileSize>377.0</docFileCab:fileSize>
                        <docFileCab:url>https://{YOUR_ACCOUNT_ID}.app.netsuite.com/core/media/media.nl?id=22619&amp;c={YOUR_ACCOUNT_ID}&amp;h={FILE_HASH}&amp;_xt=.csv</docFileCab:url>
                        <docFileCab:textFileEncoding>_utf8</docFileCab:textFileEncoding>
                        <docFileCab:isOnline>false</docFileCab:isOnline>
                        <docFileCab:isInactive>false</docFileCab:isInactive>
                        <docFileCab:class>none</docFileCab:class>
                        <docFileCab:department>none</docFileCab:department>
                        <docFileCab:isPrivate>false</docFileCab:isPrivate>
                        <docFileCab:owner internalId="54576">
                            <platformCore:name>4306</platformCore:name>
                        </docFileCab:owner>
                        <docFileCab:lastModifiedDate>2024-09-13T11:33:03.000-07:00</docFileCab:lastModifiedDate>
                        <docFileCab:createdDate>2024-09-13T11:33:03.000-07:00</docFileCab:createdDate>
                    </platformCore:record>
                </platformCore:recordList>
            </platformCore:searchResult>
        </searchResponse>
    </soapenv:Body>
</soapenv:Envelope>
```

## file_cabinet

Request:
```
POST /services/NetSuitePort_2023_2 HTTP/1.1
Content-Type: text/xml
SOAPAction: get
User-Agent: PostmanRuntime/7.41.2
Accept: */*
Host: {YOUR_ACCOUNT_ID}.suitetalk.api.netsuite.com
Accept-Encoding: gzip, deflate, br
Connection: keep-alive
Content-Length: 1203

<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns="http://www.w3.org/2001/XMLSchema">
<soapenv:Header>
<ns:tokenPassport xmlns:ns="urn:messages_2023_2.platform.webservices.netsuite.com">
<ns:account>{YOUR_ACCOUNT_ID}</ns:account>
<ns:consumerKey>{YOUR_CONSUMER_KEY}</ns:consumerKey>
<ns:token>{YOUR_TOKEN_ID}</ns:token>
<ns:nonce>alphabravo</ns:nonce>
<ns:timestamp>1726258464</ns:timestamp>
<ns:signature algorithm="HMAC_SHA256">{YOUR_SIGNATURE}</ns:signature>
</ns:tokenPassport>
</soapenv:Header>
<soapenv:Body>
<get xmlns="urn:messages_2023_2.platform.webservices.netsuite.com" xsi:type="GetRequest">
<baseRef xmlns="urn:core_2023_2.platform.webservices.netsuite.com" xsi:type="RecordRef" internalId="22519" type="file"/>
</get>
</soapenv:Body>
</soapenv:Envelope>
```

Response:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <soapenv:Header>
        <platformMsgs:documentInfo xmlns:platformMsgs="urn:messages_2023_2.platform.webservices.netsuite.com">
            <platformMsgs:nsId>WEBSERVICES_{YOUR_ACCOUNT_ID}_091320243183193761861929671_f7cfdf57</platformMsgs:nsId>
        </platformMsgs:documentInfo>
    </soapenv:Header>
    <soapenv:Body>
        <getResponse xmlns="urn:messages_2023_2.platform.webservices.netsuite.com">
            <readResponse>
                <platformCore:status isSuccess="true" xmlns:platformCore="urn:core_2023_2.platform.webservices.netsuite.com"/>
                <record internalId="22519" xsi:type="docFileCab:File" xmlns:docFileCab="urn:filecabinet_2023_2.documents.webservices.netsuite.com">
                    <docFileCab:name>example_report.csv</docFileCab:name>
                    <docFileCab:mediaTypeName>CSV File</docFileCab:mediaTypeName>
                    <docFileCab:fileType>_CSV</docFileCab:fileType>
                    <docFileCab:content>{YOUR_BASE_64_ENCODED_FILE_CONTENT}</docFileCab:content>
                    <docFileCab:folder internalId="5334" xmlns:platformCore="urn:core_2023_2.platform.webservices.netsuite.com">
                        <platformCore:name>Reports : Example Reports</platformCore:name>
                    </docFileCab:folder>
                    <docFileCab:fileSize>377.0</docFileCab:fileSize>
                    <docFileCab:url>https://{YOUR_ACCOUNT_ID}.app.netsuite.com/core/media/media.nl?id=22519&amp;c={YOUR_ACCOUNT_ID}&amp;h={FILE_HASH}&amp;_xt=.csv</docFileCab:url>
                    <docFileCab:textFileEncoding>_utf8</docFileCab:textFileEncoding>
                    <docFileCab:isOnline>false</docFileCab:isOnline>
                    <docFileCab:isInactive>false</docFileCab:isInactive>
                    <docFileCab:class>none</docFileCab:class>
                    <docFileCab:department>none</docFileCab:department>
                    <docFileCab:isPrivate>false</docFileCab:isPrivate>
                    <docFileCab:owner internalId="54576" xmlns:platformCore="urn:core_2023_2.platform.webservices.netsuite.com">
                        <platformCore:name>4306</platformCore:name>
                    </docFileCab:owner>
                    <docFileCab:lastModifiedDate>2024-09-11T11:30:38.000-07:00</docFileCab:lastModifiedDate>
                    <docFileCab:createdDate>2024-09-11T11:28:51.000-07:00</docFileCab:createdDate>
                </record>
            </readResponse>
        </getResponse>
    </soapenv:Body>
</soapenv:Envelope>
```