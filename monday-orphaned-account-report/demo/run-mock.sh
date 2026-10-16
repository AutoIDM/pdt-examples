#!/usr/bin/env bash
# All-mock demo: fake Monday and fake Entra, then `pdt run`.
set -euo pipefail
source "$(dirname "$0")/lib.sh"
demo_need_pdt
demo_start_fakes --monday
demo_export_fake_entra
export PDT_MONDAY_API_TOKEN="demo-monday-token"
export PDT_MONDAY_API_URL="http://127.0.0.1:${MONDAY_PORT}/v2"
cd "$(demo_root)"
pdt run monday-orphaned-account-report
