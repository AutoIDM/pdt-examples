#!/usr/bin/env bash
# Real Monday API plus the fake Entra. The token file is not printed or stored.
# Usage: run-real-monday.sh path/to/monday-api-token.txt
set -euo pipefail
source "$(dirname "$0")/lib.sh"

token_file="${1:-${PDT_MONDAY_TOKEN_FILE:-}}"
if [[ -z "$token_file" || ! -f "$token_file" ]]; then
  echo "usage: $0 path/to/monday-api-token.txt" >&2
  echo "The file should contain only the token. It is exported as PDT_MONDAY_API_TOKEN and not printed." >&2
  exit 1
fi

demo_need_pdt
demo_start_fakes
demo_export_fake_entra
# Always take the token from the file so a leftover demo value cannot win.
PDT_MONDAY_API_TOKEN="$(tr -d '[:space:]' < "$token_file")"
if [[ -z "${PDT_MONDAY_API_TOKEN}" ]]; then
  echo "Monday token file is empty" >&2
  exit 1
fi
export PDT_MONDAY_API_TOKEN
# Empty wins over a .env value, so this run uses https://api.monday.com/v2.
export PDT_MONDAY_API_URL=
cd "$(demo_root)"
pdt run monday-orphaned-account-report
