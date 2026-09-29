#!/usr/bin/env bash
set -euo pipefail
umask 077

# Salesforce sandbox OAuth helper:
# - First run: authorization-code + PKCE -> refresh token -> rotate once
#   (listens on the callback URL port; falls back to pasting the URL)
# - Later runs: rotate the saved refresh token and replace it atomically
#
# Required:
#   TAP_SALESFORCE_CLIENT_ID
#   TAP_SALESFORCE_CLIENT_SECRET
#
# Optional:
#   SF_ENV_FILE      default: .env next to this script (loaded if present)
#   SF_LOGIN_URL     default: https://resourceful-panda-wslf1r-dev-ed.trailblaze.my.salesforce.com
#   SF_CALLBACK_URL  default: https://localhost:1717/callback
#   SF_TLS_CERT      PEM certificate for the https listener
#   SF_TLS_KEY       PEM private key for the https listener
#                    (default: a self-signed localhost pair made for this run)
#   SF_TOKEN_FILE    default: .salesforce-oauth.json
#
# Usage:
#   ./retrieve_sf_refresh_token.sh
#   ./retrieve_sf_refresh_token.sh --reauth
#   ./retrieve_sf_refresh_token.sh --rotate
#   ./retrieve_sf_refresh_token.sh --print-env

# Load .env from the project directory when present; shell env still wins.
SF_ENV_FILE="${SF_ENV_FILE:-$(dirname "$0")/.env}"
if [[ -f "$SF_ENV_FILE" ]]; then
  sf_env_tmp="$(mktemp)"
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line#export }"
    [[ "$line" =~ ^[[:space:]]*(#|$) ]] && continue
    key="${line%%=*}"
    [[ -n "${!key:-}" ]] && continue
    printf '%s\n' "$line" >> "$sf_env_tmp"
  done < "$SF_ENV_FILE"
  set -a
  # shellcheck disable=SC1090
  source "$sf_env_tmp"
  set +a
  rm -f "$sf_env_tmp"
fi

SF_LOGIN_URL="${SF_LOGIN_URL:-https://resourceful-panda-wslf1r-dev-ed.trailblaze.my.salesforce.com}"
SF_CALLBACK_URL="${SF_CALLBACK_URL:-https://localhost:1717/callback}"
SF_TOKEN_FILE="${SF_TOKEN_FILE:-.salesforce-oauth.json}"

: "${TAP_SALESFORCE_CLIENT_ID:?Set TAP_SALESFORCE_CLIENT_ID to the External Client App consumer key}"
: "${TAP_SALESFORCE_CLIENT_SECRET:?Set TAP_SALESFORCE_CLIENT_SECRET to the External Client App consumer secret}"

for cmd in curl openssl python3; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "Missing required command: $cmd" >&2
    exit 1
  }
done

json_field() {
  local field="$1"
  python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
except Exception as exc:
    print(f"Invalid JSON response: {exc}", file=sys.stderr)
    sys.exit(2)
value = data.get(sys.argv[1], "")
if value is None:
    value = ""
print(value)
' "$field"
}

check_oauth_response() {
  local response="$1"
  local error
  error="$(printf '%s' "$response" | json_field error)"
  if [[ -n "$error" ]]; then
    local description
    description="$(printf '%s' "$response" | json_field error_description)"
    echo "Salesforce OAuth error: $error" >&2
    [[ -n "$description" ]] && echo "$description" >&2
    exit 1
  fi
}

save_response() {
  local response="$1"
  local dir tmp
  dir="$(dirname "$SF_TOKEN_FILE")"
  mkdir -p "$dir"
  tmp="$(mktemp "${SF_TOKEN_FILE}.tmp.XXXXXX")"
  printf '%s\n' "$response" > "$tmp"
  chmod 600 "$tmp"
  mv "$tmp" "$SF_TOKEN_FILE"
}

open_browser() {
  local url="$1"
  if command -v open >/dev/null 2>&1; then
    open "$url"
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$url" >/dev/null 2>&1 &
  else
    echo "Open this URL in a browser:" >&2
    echo "$url" >&2
  fi
}

make_pkce_verifier() {
  openssl rand -base64 64 \
    | tr '+/' '-_' \
    | tr -d '=\n'
}

make_pkce_challenge() {
  local verifier="$1"
  printf '%s' "$verifier" \
    | openssl dgst -sha256 -binary \
    | openssl base64 -A \
    | tr '+/' '-_' \
    | tr -d '='
}

build_authorize_url() {
  local verifier="$1"
  local challenge="$2"
  local state="$3"

  SF_PKCE_CHALLENGE="$challenge" SF_OAUTH_STATE="$state" python3 - <<'PY'
import os
from urllib.parse import urlencode

base = os.environ["SF_LOGIN_URL"].rstrip("/")
params = {
    "response_type": "code",
    "client_id": os.environ["TAP_SALESFORCE_CLIENT_ID"],
    "redirect_uri": os.environ["SF_CALLBACK_URL"],
    "scope": "api refresh_token",
    "code_challenge": os.environ["SF_PKCE_CHALLENGE"],
    "code_challenge_method": "S256",
    "state": os.environ["SF_OAUTH_STATE"],
}
print(base + "/services/oauth2/authorize?" + urlencode(params))
PY
}

exchange_code() {
  local code="$1"
  local verifier="$2"

  local body
  body="$(
    SF_AUTH_CODE="$code" SF_PKCE_VERIFIER="$verifier" python3 - <<'PY'
import os
from urllib.parse import urlencode

print(urlencode({
    "grant_type": "authorization_code",
    "code": os.environ["SF_AUTH_CODE"],
    "client_id": os.environ["TAP_SALESFORCE_CLIENT_ID"],
    "client_secret": os.environ["TAP_SALESFORCE_CLIENT_SECRET"],
    "redirect_uri": os.environ["SF_CALLBACK_URL"],
    "code_verifier": os.environ["SF_PKCE_VERIFIER"],
}))
PY
  )"

  printf '%s' "$body" \
    | curl -sS \
        -X POST \
        -H 'Content-Type: application/x-www-form-urlencoded' \
        --data-binary @- \
        "${SF_LOGIN_URL%/}/services/oauth2/token"
}

rotate_refresh_token() {
  local refresh_token="$1"

  local body
  body="$(
    SF_CURRENT_REFRESH_TOKEN="$refresh_token" python3 - <<'PY'
import os
from urllib.parse import urlencode

print(urlencode({
    "grant_type": "refresh_token",
    "client_id": os.environ["TAP_SALESFORCE_CLIENT_ID"],
    "client_secret": os.environ["TAP_SALESFORCE_CLIENT_SECRET"],
    "refresh_token": os.environ["SF_CURRENT_REFRESH_TOKEN"],
}))
PY
  )"

  printf '%s' "$body" \
    | curl -sS \
        -X POST \
        -H 'Content-Type: application/x-www-form-urlencoded' \
        --data-binary @- \
        "${SF_LOGIN_URL%/}/services/oauth2/token"
}

# Bind the callback port before the browser opens, then serve one request in
# the background. Prints three lines: the path of a file that receives
# "code\nstate", the pid of the background server, and the directory that
# holds a generated certificate (empty when SF_TLS_CERT was given).
# Fails when the host is not localhost, the port is busy, or no certificate
# can be made for an https callback.
listen_for_callback() {
  local out tls_dir=""
  out="$(mktemp)"
  echo "$out"
  if [[ "$SF_CALLBACK_URL" == https://* && -z "${SF_TLS_CERT:-}" ]]; then
    tls_dir="$(mktemp -d)"
    openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj "/CN=localhost" \
      -addext "subjectAltName=DNS:localhost,IP:127.0.0.1" \
      -keyout "$tls_dir/key.pem" -out "$tls_dir/cert.pem" >/dev/null 2>&1 || return 1
    SF_TLS_CERT="$tls_dir/cert.pem"
    SF_TLS_KEY="$tls_dir/key.pem"
  fi
  SF_CALLBACK_OUT="$out" SF_TLS_CERT="${SF_TLS_CERT:-}" SF_TLS_KEY="${SF_TLS_KEY:-}" \
    SF_TLS_DIR="$tls_dir" python3 - <<'PY' || return 1
import os, ssl, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlsplit, parse_qs

cb = urlsplit(os.environ["SF_CALLBACK_URL"])
if cb.hostname not in ("localhost", "127.0.0.1"):
    sys.exit(1)
try:
    server = HTTPServer((cb.hostname, cb.port or (443 if cb.scheme == "https" else 80)), BaseHTTPRequestHandler)
    if cb.scheme == "https":
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(os.environ["SF_TLS_CERT"], os.environ["SF_TLS_KEY"] or None)
        server.socket = ctx.wrap_socket(server.socket, server_side=True)
except (OSError, ssl.SSLError):
    sys.exit(1)

pid = os.fork()
if pid:
    print(pid)
    print(os.environ["SF_TLS_DIR"])
    sys.exit(0)
devnull = os.open(os.devnull, os.O_RDWR)
for fd in (0, 1, 2):
    os.dup2(devnull, fd)

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass
    def do_GET(self):
        q = parse_qs(urlsplit(self.path).query)
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Authorization received. You can close this tab.\n")
        with open(os.environ["SF_CALLBACK_OUT"], "w") as f:
            f.write(q.get("code", [""])[0] + "\n" + q.get("state", [""])[0] + "\n")
        self.server.done = True

server.RequestHandlerClass = Handler
server.done = False
while not server.done:
    # A browser that refuses the self-signed certificate closes the socket
    # mid-handshake; keep serving so the next attempt still lands.
    try:
        server.handle_request()
    except ssl.SSLError:
        pass
PY
}

authorize() {
  local verifier challenge state auth_url listener listener_pid tls_dir callback_file callback_input parsed code returned_state response refresh_token rotated_response rotated_refresh_token

  verifier="$(make_pkce_verifier)"
  challenge="$(make_pkce_challenge "$verifier")"
  state="$(openssl rand -hex 16)"

  export SF_LOGIN_URL SF_CALLBACK_URL TAP_SALESFORCE_CLIENT_ID TAP_SALESFORCE_CLIENT_SECRET
  auth_url="$(build_authorize_url "$verifier" "$challenge" "$state")"

  echo "Opening Salesforce authorization in your browser..." >&2
  echo "Log in as the Salesforce user that should own this refresh-token chain." >&2
  echo >&2

  listener_pid=""
  if listener="$(listen_for_callback)"; then
    callback_file="$(printf '%s\n' "$listener" | sed -n '1p')"
    listener_pid="$(printf '%s\n' "$listener" | sed -n '2p')"
    tls_dir="$(printf '%s\n' "$listener" | sed -n '3p')"
    echo "Listening on $SF_CALLBACK_URL for the redirect." >&2
    if [[ -n "$tls_dir" ]]; then
      echo "The listener uses a self-signed certificate; tell the browser to continue past its warning." >&2
    fi
  else
    callback_file=""
    tls_dir=""
    echo "Could not listen on $SF_CALLBACK_URL (port busy, host is not localhost, or certificate setup failed)." >&2
  fi
  echo "If the browser does not open, use this URL:" >&2
  echo "$auth_url" >&2
  echo >&2
  echo "After Salesforce redirects, you can also paste the FULL URL from the address bar here." >&2

  open_browser "$auth_url"

  callback_input=""
  printf 'Callback URL: ' >&2
  while :; do
    if [[ -n "$callback_file" && -s "$callback_file" ]]; then
      echo >&2
      callback_input="$(cat "$callback_file")"
      break
    fi
    if read -r -t 1 callback_input; then
      [[ -n "$callback_input" ]] && break
      printf 'Callback URL: ' >&2
    fi
  done
  [[ -n "$callback_file" ]] && rm -f "$callback_file"
  # The listener exits by itself once it has served the redirect.
  [[ -n "$listener_pid" ]] && { kill "$listener_pid" 2>/dev/null || true; }
  [[ -n "$tls_dir" ]] && rm -rf "$tls_dir"

  parsed="$(
    SF_CALLBACK_INPUT="$callback_input" python3 - <<'PY'
import os
from urllib.parse import urlsplit, parse_qs

value = os.environ["SF_CALLBACK_INPUT"].strip()

# Accept the listener output ("code\nstate"), the full callback URL, or just the code.
if "\n" in value:
    print(value)
elif "://" not in value:
    print(value)
    print("")
else:
    q = parse_qs(urlsplit(value).query)
    print(q.get("code", [""])[0])
    print(q.get("state", [""])[0])
PY
  )"

  code="$(printf '%s\n' "$parsed" | sed -n '1p')"
  returned_state="$(printf '%s\n' "$parsed" | sed -n '2p')"

  [[ -n "$code" ]] || {
    echo "Could not find ?code= in the callback URL." >&2
    exit 1
  }

  if [[ -n "$returned_state" && "$returned_state" != "$state" ]]; then
    echo "OAuth state mismatch; refusing to exchange the code." >&2
    exit 1
  fi

  echo "Exchanging authorization code..." >&2
  response="$(exchange_code "$code" "$verifier")"
  check_oauth_response "$response"

  refresh_token="$(printf '%s' "$response" | json_field refresh_token)"
  [[ -n "$refresh_token" ]] || {
    echo "Salesforce did not return a refresh_token." >&2
    echo "Confirm the app has the refresh_token/offline_access scope." >&2
    exit 1
  }

  # Your External Client App has refresh-token rotation enabled.
  # Rotate immediately so we verify the flow and persist only the current token.
  echo "Initial refresh token received; rotating it once..." >&2
  rotated_response="$(rotate_refresh_token "$refresh_token")"
  check_oauth_response "$rotated_response"

  rotated_refresh_token="$(printf '%s' "$rotated_response" | json_field refresh_token)"
  [[ -n "$rotated_refresh_token" ]] || {
    echo "Refresh-token rotation is expected, but Salesforce returned no new refresh_token." >&2
    echo "Not overwriting the token file." >&2
    exit 1
  }

  save_response "$rotated_response"
  echo "Saved current token response to: $SF_TOKEN_FILE" >&2
}

rotate_saved() {
  [[ -f "$SF_TOKEN_FILE" ]] || {
    echo "No token file found at $SF_TOKEN_FILE; run without --rotate to authorize first." >&2
    exit 1
  }

  local current response new_refresh
  current="$(json_field refresh_token < "$SF_TOKEN_FILE")"
  [[ -n "$current" ]] || {
    echo "Token file contains no refresh_token." >&2
    exit 1
  }

  echo "Rotating saved refresh token..." >&2
  response="$(rotate_refresh_token "$current")"
  check_oauth_response "$response"

  new_refresh="$(printf '%s' "$response" | json_field refresh_token)"
  [[ -n "$new_refresh" ]] || {
    echo "Salesforce returned no replacement refresh_token." >&2
    echo "Because rotation is enabled, refusing to overwrite the current token file." >&2
    exit 1
  }

  save_response "$response"
  echo "Saved rotated token response to: $SF_TOKEN_FILE" >&2
}

print_current() {
  [[ -f "$SF_TOKEN_FILE" ]] || {
    echo "No token file found at $SF_TOKEN_FILE." >&2
    exit 1
  }

  local refresh_token access_token instance_url
  refresh_token="$(json_field refresh_token < "$SF_TOKEN_FILE")"
  access_token="$(json_field access_token < "$SF_TOKEN_FILE")"
  instance_url="$(json_field instance_url < "$SF_TOKEN_FILE")"

  echo
  echo "Current credentials/token values:"
  printf 'TAP_SALESFORCE_CLIENT_ID=%q\n' "$TAP_SALESFORCE_CLIENT_ID"
  printf 'TAP_SALESFORCE_CLIENT_SECRET=%q\n' "$TAP_SALESFORCE_CLIENT_SECRET"
  printf 'TAP_SALESFORCE_REFRESH_TOKEN=%q\n' "$refresh_token"
  printf '# access_token=%q\n' "$access_token"
  printf '# instance_url=%q\n' "$instance_url"
}

print_meltano_env() {
  [[ -f "$SF_TOKEN_FILE" ]] || {
    echo "No token file found at $SF_TOKEN_FILE." >&2
    exit 1
  }

  local refresh_token
  refresh_token="$(json_field refresh_token < "$SF_TOKEN_FILE")"

  printf 'export TAP_SALESFORCE_CLIENT_ID=%q\n' "$TAP_SALESFORCE_CLIENT_ID"
  printf 'export TAP_SALESFORCE_CLIENT_SECRET=%q\n' "$TAP_SALESFORCE_CLIENT_SECRET"
  printf 'export TAP_SALESFORCE_REFRESH_TOKEN=%q\n' "$refresh_token"
}

case "${1:-auto}" in
  auto)
    if [[ -f "$SF_TOKEN_FILE" ]]; then
      rotate_saved
    else
      authorize
    fi
    print_current
    ;;
  --reauth)
    authorize
    print_current
    ;;
  --rotate)
    rotate_saved
    print_current
    ;;
  --print-env)
    print_meltano_env
    ;;
  *)
    echo "Usage: $0 [--reauth|--rotate|--print-env]" >&2
    exit 2
    ;;
esac

