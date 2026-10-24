# salesforce-netsuite-customer-sync

This app copies Salesforce accounts and contacts into NetSuite. Salesforce is the source of truth. Each Salesforce Account becomes a NetSuite customer. Each Salesforce Contact becomes a NetSuite contact under that customer. The NetSuite `externalId` field holds the Salesforce record id, so the two systems stay linked without a mapping table.

It runs like any other pdt app. `run.py` is the entry point. The folder is also a complete Meltano project: `meltano.yml`, `transform/` for dbt, `autoidm-transform/` for the Python business logic, and a DuckDB file for the run state.

## What gets written

Customer fields: `companyname` from Account Name, `phone`, `fax`, `url` from Website, and `comments` from Description.

Contact fields: `firstname`, `lastname`, `salutation`, `title`, `email`, `phone`, `mobilephone`, `fax`, and `company`. `company` is the NetSuite internal id of the customer the contact belongs to.

Two rules decide what the sync leaves alone. A NULL in a desired column means "do not manage this field", and `transform/macros/autoidm_matcher.sql` reports no change for it. To clear a field that holds a value, the transform writes the string `_blank_`. It writes that only when NetSuite holds a value to clear.

A contact whose Account has no NetSuite customer yet gets a NULL `company`. It syncs without a parent, and the transform records a send-once notification. The next run links it, because the customer exists by then.

## The four Meltano jobs

- `extract` drops the two source schemas, then loads `tap-salesforce` and `tap-netsuite` into DuckDB through `target-duckdb`.
- `transform` runs `dbt:pre_python` for the staging models, then `autoidm-transform` for the desired state, then `dbt:post_python` for the match and target tables.
- `artifacts` exports the `autoidm` and `autoidm_state` tables to CSV through `target-csv-artifacts`, so a person can review pending changes before a load.
- `load` reads the four `netsuite_*_target_*` tables with `tap-duckdb` and writes them to `target-netsuite`.

`run.py` runs `extract`, `transform`, and `artifacts` before `load`. Each run uses a fresh local directory. It pulls `state/sync.duckdb` from the PDT Store, uploads CSV artifacts to that run's artifact folder, and pushes the closed DuckDB file back to `state/` after a successful load.

## Running it locally

1. Copy the names in `env.template` into a `.env` file in this folder or the project root, and fill them in.
2. Run `pdt run salesforce-netsuite-customer-sync`.
3. For direct Meltano commands, create the database directory and set `DUCKDB_PATH` to an absolute file path.
4. Set `ARTIFACTS_PATH` to an output directory with a trailing slash.
5. Run `meltano --environment dev install`, then `meltano --environment dev run --force extract transform artifacts`.

`pdt-cli[apps]==0.1.1` ships the storage API that `run.py` uses. PDT supplies `PDT_STORAGE_URL` for the app's storage location. Without that variable, the storage API uses `.pdt/storage/<app>/` under the project root, so a local `pdt run` and a cloud job behave the same way.

Artifacts remain available if NetSuite loading fails. State uploads occur only after a successful load. The store has no abort call, so `run.py` deletes the state lock itself when Meltano fails; otherwise the next run would wait for the lock's 30 minute expiry. Local run files remain under this app's `.pdt/runs/` for inspection.

`tap-duckdb` is pinned to a commit that bumps its SDK and DuckDB versions, because the released version does not install on Python 3.12. The project pins DuckDB 1.5.5 for the tap, the target, dbt, and the transform package. Move `pip_url` to the released package once one ships with those versions.

## The refresh token

The `Dockerfile` runs `uv run --script run.py --install-only` at image build time, so `meltano install` runs once when the image is built instead of at every run. Run `meltano install` yourself before the first local `uv run --script run.py`.

`TAP_SALESFORCE_REFRESH_TOKEN_STORE_HOOK` names an executable that writes the new token where the next run's configured token comes from. It runs with no arguments and receives the new token on stdin.

The default is `scripts/sf-refresh-token-keyvault.py`. `run.py` sets it when you have not. It writes `TAP_SALESFORCE_REFRESH_TOKEN` into the app's deployed secret (the Key Vault secret on Azure, Secrets Manager on AWS, Secret Manager on Google Cloud), which `pdt deploy` grants the job the right to update. On your own computer it writes the nearest `.env` file and then runs `pdt secrets salesforce-netsuite-customer-sync set TAP_SALESFORCE_REFRESH_TOKEN` with the same value, so a local run keeps the deployed job's next login working. That step needs you to be signed in to the cloud provider, and it is a note, not an error, when the app is not deployed. The hook's log lines say where the value went. Either way `pdt secrets salesforce-netsuite-customer-sync` shows the rotated token, and `pdt secrets salesforce-netsuite-customer-sync get` copies it down before a deploy from a stale `.env` would overwrite it.

The other choice is `scripts/sf-refresh-token-gitlab.py`, which keeps the copy in a GitLab CI/CD project variable. It needs `GITLAB_TOKEN`, a project or group access token with the `api` scope and the Maintainer role.

## Two details worth knowing before you edit the dbt models

Every desired row carries its action in `_autoidm__action`. `transform/macros/autoidm_update.sql` is copied from the copier template with one change: its `where` clause filters on `_autoidm__action` instead of `action`. `target-netsuite` dispatches on the same column. The match models pass it to `autoidm_matcher` as an ignored column.

Every column in this project is lower case. The vendored macros write unquoted identifiers, and DuckDB keeps those names. The NetSuite sinks map them back to the camel case names the NetSuite REST API expects, for example `companyname` to `companyName`.
