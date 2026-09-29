# target-netsuite

`target-netsuite` is a Singer target for NetSuite.

Build with the [Meltano Target SDK](https://sdk.meltano.com).

## Installation

An example GitLab installation command:

```bash
pipx install git+https://gitlab.com/AutoIDM/tap-asana.git
```

## Configuration

### Accepted Config Options

| Setting | Required | Default | Description |
|:--------|:--------:|:-------:|:------------|
| production | True     |       0 | If set to false, will fail if a Production account ID is used. If set to true, will fail if a Sandbox or Release Preview account ID is used. |
| account_id | True     | None    | Your NetSuite instance's account ID. For production accounts, this can be found at the beginning of your NetSuite URL. For example, if your URL is `https://1234567.app.netsuite.com`, your account ID is `1234567`. For Sandbox and Release Preview accounts, refer to the [docs](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_1498754928.html). |
| client_id | True     | None    | Your NetSuite client ID, obtained when you set up OAuth 2.0. For more information, check the [docs](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_157771733782.html). Note that both your client ID and client secret are sensitive . From the [docs](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_157771733782.html): "If you lose or forget the client ID and client secret, you will have to reset them on the Integration page, to obtain new values. Treat these values as you would a password. |
| certificate_id | True     | None    | Your certificate ID, displayed when setting up your private key. You can learn more about certificates from the [docs](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_162686838198.html). |
| private_key | True     | None    | A certificate representing a private key, used for JWT Auth. You may provide this value either as a file path or directly as a certificate.You can learn more about certificates from the [docs](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_162686838198.html). |
| api_timeout | True     |      90 | Timeout in seconds when accessing the API |
| max_errors | True     |      10 | Maximum number individual record failures before failing the entire target. Set to -1 to allow any number of failures. |
| add_record_metadata | False    | None    | Add metadata to records. |
| load_method | False    | append-only | The method to use when loading data into the destination. `append-only` will always write all input records whether that records already exists or not. `upsert` will update existing records and insert new records. `overwrite` will delete all existing records and insert all input records. |
| batch_size_rows | False    | None    | Maximum number of rows in each batch. |
| validate_records | False    |       1 | Whether to validate the schema of the incoming streams. |
| stream_maps | False    | None    | Config object for stream maps capability. For more information check out [Stream Maps](https://sdk.meltano.com/en/latest/stream_maps.html). |
| stream_map_config | False    | None    | User-defined config values to be used within map expressions. |
| faker_config | False    | None    | Config for the [`Faker`](https://faker.readthedocs.io/en/master/) instance variable `fake` used within map expressions. Only applicable if the plugin specifies `faker` as an addtional dependency (through the `singer-sdk` `faker` extra or directly). |
| faker_config.seed | False    | None    | Value to seed the Faker generator for deterministic output: https://faker.readthedocs.io/en/master/#seeding-the-generator |
| faker_config.locale | False    | None    | One or more LCID locale strings to produce localized output for: https://faker.readthedocs.io/en/master/#localization |
| flattening_enabled | False    | None    | 'True' to enable schema flattening and automatically expand nested properties. |
| flattening_max_depth | False    | None    | The max depth to flatten schemas. |

A full list of supported settings and capabilities for this
target is available by running:

```bash
target-netsuite --about
```

### Configure using environment variables

This Singer target will automatically import any environment variables within the working directory's
`.env` if the `--config=ENV` is provided, such that config values will be considered if a matching
environment variable is set either in the terminal context or in the `.env` file.

### Source Authentication and Authorization

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

## Usage

You can easily run `target-netsuite` by itself or in a pipeline using [Meltano](https://meltano.com/).

### Executing the Target Directly

```bash
target-netsuite --version
target-netsuite --help
# Test using the "Carbon Intensity" sample:
tap-carbon-intensity | target-netsuite --config /path/to/target-netsuite-config.json
```

## Developer Resources

Follow these instructions to contribute to this project.

### Initialize your Development Environment

```bash
pipx install poetry
poetry install
```

### Generating a JWT Token for Netsuite
Check out the scripts folder in tap-netsuite there's a script to generate tokens there

### Create and Run Tests

Create tests within the `tests` subfolder and
  then run:

```bash
poetry run pytest
```

You can also test the `target-netsuite` CLI interface directly using `poetry run`:

```bash
poetry run target-netsuite --help
```

### Testing with [Meltano](https://meltano.com/)

_**Note:** This target will work in any Singer environment and does not require Meltano.
Examples here are for convenience and to streamline end-to-end orchestration scenarios._

Next, install Meltano (if you haven't already) and any needed plugins:

```bash
# Install meltano
pipx install meltano
# Initialize meltano within this directory
cd target-netsuite
meltano install
```

Now you can test and orchestrate using Meltano:

```bash
# Test invocation:
meltano invoke target-netsuite --version
# OR run a test `elt` pipeline with the Carbon Intensity sample tap:
meltano run tap-carbon-intensity target-netsuite
```

### SDK Dev Guide

See the [dev guide](https://sdk.meltano.com/en/latest/dev_guide.html) for more instructions on how to use the Meltano Singer SDK to
develop your own Singer taps and targets.
