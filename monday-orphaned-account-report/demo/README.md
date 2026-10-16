# Monday orphaned-account report demo

Both commands run `pdt run monday-orphaned-account-report` from the repo root. Findings print on the terminal because no email transport is set. Nothing here is a real secret.

Install once:

```bash
uv tool install pdt-cli
```

## (a) Real Monday, fake Entra

Uses `https://api.monday.com/v2` and a local Entra token plus Graph `/users` stand-in. `dvisch@autoidm.com` is in that directory and disabled, so an active Monday user with that email is reported as orphaned.

Pass a file that contains only the Monday token. The script exports `PDT_MONDAY_API_TOKEN` and does not print it.

```bash
monday-orphaned-account-report/demo/run-real-monday.sh path/to/monday-api-token.txt
```

Leave `PDT_MONDAY_API_URL` unset (the script does) when you want the real Monday host. To point the same app at a real Entra tenant later, unset `PDT_GRAPH_BASE_URL` and `PDT_ENTRA_LOGIN_BASE` and set the Azure variables from `env.template`.

## (b) All mock

Fake Monday GraphQL users and the same fake Entra. Expect three orphaned Contoso accounts: Grace Hopper (disabled in Entra), Linus Torvalds (missing), and Katherine Johnson (Monday email differs from the Entra sign-in name).

```bash
monday-orphaned-account-report/demo/run-mock.sh
```
