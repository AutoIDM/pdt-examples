# vendor-status-alerts

This app mails an IT team one digest of new vendor status events. It reads three sources every hour: Adobe incidents and maintenance from status.adobe.com, CISA advisories and the Known Exploited Vulnerabilities (KEV) catalog, and Microsoft 365 service health and Message center posts for your tenant. It keeps every item in a DuckDB database and mails each item one time.

Adobe and CISA are public, so the app runs with no credentials. Mail starts when you set `TARGET_APPRISE_URIS`. Microsoft 365 starts when you set `PDT_AZURE_TENANT_ID` and the other Entra values. `env.template` describes each one.

## What gets mailed

A run builds one digest with a section for each source and sends it through target-apprise. An item goes into the digest when it is new, or when its status changed since the last digest (for example an Adobe incident that moved from Opened to Closed). An item that changed more than `notify_lookback_days` ago stays in the database but is never mailed, which also keeps the first digest after a deploy short.

These rules decide which items are mailed:

- Adobe: only the products and clouds in `adobe_products` in `config.yml`. The default list holds Creative Cloud, Document Cloud, Administrative Consoles, and Adobe Account Management. An empty list mails every Adobe product, about 25 items a day.
- CISA advisories: every advisory except the industrial control system advisories (`ics-advisories`) and the "CISA Adds ... Known Exploited Vulnerabilities" alerts, because each KEV entry is mailed by itself. Change the `cisa_advisories` part of `transform/models/vendor_events.sql` to mail more.
- CISA KEV: every new entry.
- Microsoft 365: every issue and every Message center post.

## The Meltano jobs

This folder is a complete Meltano project. Three Singer taps in `extract/` read the sources. `target-duckdb` loads each one into its own schema: `tap_adobe_status`, `tap_cisa`, and `tap_ms365_service_health`. Each row is updated by its primary key, so the tables keep items that the source no longer lists.

- `extract-adobe`, `extract-cisa`, and `extract-microsoft` each run one tap into DuckDB.
- `transform` runs dbt. The `vendor_events` model puts every source into one shape and adds new items to `autoidm_state.send_once_notifications`. The `unsent_send_once_notifications` model builds the digest from the rows that are not sent.
- `notify` reads the digest with `tap-duckdb`, sends it with `target-apprise`, and then runs the `mark_sent` dbt macro. A failed send stops the job before `mark_sent`, so the next run sends the same rows again.

This is the send-once pattern of the AutoIDM customer projects. `run.py` runs each extract job by itself, so a failed source does not stop the digest from the other sources. The run then exits with code 3 so the failure shows. `run.py --install-only` runs `meltano install`. The Dockerfile runs it when it builds the image.

## The database

The DuckDB file is `state/vendor_status.duckdb` in the app's pdt storage. `run.py` pulls it before a run and pushes it back after the run, also after a failed run, because the push releases the storage lock. Without `PDT_STORAGE_URL` the file is `.pdt/storage/vendor-status-alerts/state/vendor_status.duckdb` in the project root. pdt sets that variable for a deployed app.

## Microsoft 365 permissions

The Entra app registration needs the Microsoft Graph application permissions `ServiceHealth.Read.All` and `ServiceMessage.Read.All`, with admin consent. A global administrator can add both with these commands, where `<client-id>` is the value of `PDT_AZURE_CLIENT_ID`:

```
pdt az ad app permission add --id <client-id> --api 00000003-0000-0000-c000-000000000000 --api-permissions 79c261e0-fe76-4144-aad5-bdc68fbe4037=Role 1b620472-6534-4fe6-9df2-4680e8aa28ec=Role
pdt az ad app permission admin-consent --id <client-id>
```

Without them the `extract-microsoft` job fails with "Microsoft Graph refused access", and the other sources still mail.

## Running it locally

1. Copy the names in `env.template` into a `.env` file in this folder or the project root, and fill in the blocks you want.
2. Run `pdt run vendor-status-alerts`.

For direct Meltano commands, set `DUCKDB_PATH` to an absolute file path in a folder that exists. Then run `meltano run --force extract-adobe extract-cisa transform`, and `meltano run --force notify` to send the digest.

To run the tests: `uv run --with pytest --with singer-sdk~=0.54.7 --with requests --with msal --with cryptography pytest tests`.

## Pinned versions

The Adobe tap reads `https://data.status.adobe.com/adobestatus/StatusEvents`, the file that status.adobe.com itself reads. The documented Adobe Status API holds the same events but needs an Adobe Developer Console project and OAuth credentials.

The CISA site answers 403 to some User-Agent values, for example `Mozilla/5.0`, so `tap-cisa` sends the default one from `requests`.

`tap-duckdb` is pinned to the same commit as in `salesforce-netsuite-customer-sync`, with `sqlalchemy<2.1`, because duckdb-engine 0.13 fails catalog discovery on SQLAlchemy 2.1. `target-apprise` is pinned to a commit on GitHub, because the PyPI release caps Python below 3.12.
