#!/usr/bin/env bash
# Shared setup for the Monday orphan-report demos. Source this; do not execute it.
# Fake values only. A real Monday token is read by run-real-monday.sh and never written here.

_DEMO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_DEMO_ROOT="$(cd "${_DEMO_DIR}/../.." && pwd)"

demo_root() {
  printf '%s\n' "$_DEMO_ROOT"
}

demo_dir() {
  printf '%s\n' "$_DEMO_DIR"
}

demo_need_pdt() {
  export PATH="${HOME}/.local/bin:${PATH}"
  if ! command -v pdt >/dev/null 2>&1; then
    echo "pdt is not on PATH. Install it with: uv tool install pdt-cli" >&2
    exit 1
  fi
}

# Start the stand-in. Pass --monday to also serve Monday.
# Sets ENTRA_PORT and, when asked, MONDAY_PORT. Leaves FAKE_PID running.
demo_start_fakes() {
  local ready
  ready="$(mktemp)"
  python3 "$(demo_dir)/fake_apis.py" --ready-file "$ready" "$@" &
  FAKE_PID=$!
  # shellcheck disable=SC2064
  trap "kill ${FAKE_PID} 2>/dev/null || true; rm -f ${ready}" EXIT
  local _i
  for _i in $(seq 1 50); do
    if [[ -s "$ready" ]]; then
      # shellcheck disable=SC1090
      source "$ready"
      rm -f "$ready"
      return 0
    fi
    if ! kill -0 "$FAKE_PID" 2>/dev/null; then
      echo "fake API process exited before it was ready" >&2
      exit 1
    fi
    sleep 0.1
  done
  echo "fake API did not become ready" >&2
  exit 1
}

demo_export_fake_entra() {
  export PDT_AZURE_TENANT_ID="11111111-1111-1111-1111-111111111111"
  export PDT_AZURE_CLIENT_ID="22222222-2222-2222-2222-222222222222"
  export PDT_AZURE_CLIENT_SECRET="demo-client-secret"
  export PDT_GRAPH_BASE_URL="http://127.0.0.1:${ENTRA_PORT}/v1.0"
  export PDT_ENTRA_LOGIN_BASE="http://127.0.0.1:${ENTRA_PORT}"
  unset PDT_AZURE_PRIVATE_KEY_B64 PDT_AZURE_PRIVATE_KEY_PATH PDT_AZURE_PRIVATE_KEY_PASSWORD
  unset PDT_SMTP_HOST PDT_SMTP_USER PDT_SMTP_PASSWORD PDT_RESEND_API_KEY PDT_SES_REGION
  unset PDT_GRAPH_MAIL_USER PDT_GRAPH_MAIL_CLIENT_ID
}
