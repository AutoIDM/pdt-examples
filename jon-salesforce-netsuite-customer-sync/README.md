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

`run.py` runs `extract`, `transform`, and `artifacts`, then `load`. Each run works in a fresh directory under `.pdt/runs/`. Before the run it pulls `state/` from PDT storage, which holds `sync.duckdb`. After the run it uploads the CSV artifacts to that run's folder, then pushes `state/` back. The push happens after a failed run too, because it releases the storage lock.

`run.py --install-only` runs `meltano install` and stops. The Dockerfile runs that at image build time, so a deployed job starts with every plugin installed.

## Running it locally

1. Copy the names in `env.template` into a `.env` file in this folder or the project root, and fill them in.
2. Run `pdt run salesforce-netsuite-customer-sync`.

For direct Meltano commands, set `DUCKDB_PATH` to an absolute file path in a directory that exists, and set `ARTIFACTS_PATH` to an output directory with a trailing slash. Then run `meltano --environment dev install` and `meltano --environment dev run --force extract transform artifacts`.

Without `PDT_STORAGE_URL`, storage lives under `.pdt/storage/<app>/` in the project root. pdt sets that variable for a deployed app.

`meltano_environment` in `config.yml` picks the Meltano environment. `dev` points at a Salesforce sandbox and a NetSuite sandbox account. `prod` points at both production systems.

`tap-duckdb` is pinned to a commit that bumps its SDK and DuckDB versions, because the released version does not install on Python 3.12. The project pins DuckDB 1.5.5 for the tap, the target, dbt, and the transform package. Move `pip_url` to the released package once one ships with those versions.

## The refresh token

Salesforce gives the tap a new refresh token on every login and invalidates the old one. The tap keeps the current token in `$XDG_DATA_HOME/autoidm/salesforce-netsuite-customer-sync/salesforce_refresh_token.json` (`%LOCALAPPDATA%\autoidm\...` on Windows) and tries that copy first at the next login. A rejected copy, or none, falls back to the configured `TAP_SALESFORCE_REFRESH_TOKEN`. On your own computer that folder persists, so several runs of the app share one token chain. A container starts with the folder empty and discards it, so every deployed run starts from the configured token.

`TAP_SALESFORCE_REFRESH_TOKEN_STORE_HOOK` names an executable that writes the new token where the next run's configured token comes from. It runs with no arguments and receives the new token on stdin.

The default is `scripts/sf-refresh-token-keyvault.py`. `run.py` sets it when you have not. It writes `TAP_SALESFORCE_REFRESH_TOKEN` into the app's deployed secret (the Key Vault secret on Azure, Secrets Manager on AWS, Secret Manager on Google Cloud), which `pdt deploy` grants the job the right to update. On your own computer it writes the nearest `.env` file and then runs `pdt secrets salesforce-netsuite-customer-sync set TAP_SALESFORCE_REFRESH_TOKEN` with the same value, so a local run keeps the deployed job's next login working. That step needs you to be signed in to the cloud provider, and it is a note, not an error, when the app is not deployed. The hook's log lines say where the value went. Either way `pdt secrets salesforce-netsuite-customer-sync` shows the rotated token, and `pdt secrets salesforce-netsuite-customer-sync get` copies it down before a deploy from a stale `.env` would overwrite it.

The other choice is `scripts/sf-refresh-token-gitlab.py`, which keeps the copy in a GitLab CI/CD project variable. It needs `GITLAB_TOKEN`, a project or group access token with the `api` scope and the Maintainer role.

## Two details worth knowing before you edit the dbt models

Every desired row carries its action in `_autoidm__action`. `transform/macros/autoidm_update.sql` is copied from the copier template with one change: its `where` clause filters on `_autoidm__action` instead of `action`. `target-netsuite` dispatches on the same column. The match models pass it to `autoidm_matcher` as an ignored column.

Every column in this project is lower case. The vendored macros write unquoted identifiers, and DuckDB keeps those names. The NetSuite sinks map them back to the camel case names the NetSuite REST API expects, for example `companyname` to `companyName`.
