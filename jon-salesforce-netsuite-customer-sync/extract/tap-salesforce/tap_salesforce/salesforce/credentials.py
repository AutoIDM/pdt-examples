import json
import logging
import os
import subprocess
import threading
from collections import namedtuple
from pathlib import Path

import requests
from simple_salesforce import SalesforceLogin

LOGGER = logging.getLogger(__name__)


OAuthCredentials = namedtuple("OAuthCredentials", ("client_id", "client_secret", "refresh_token"))

PasswordCredentials = namedtuple("PasswordCredentials", ("username", "password", "security_token"))


def parse_credentials(config):
    for cls in reversed((OAuthCredentials, PasswordCredentials)):
        creds = cls(*(config.get(key) for key in cls._fields))
        if all(creds):
            return creds

    raise Exception("Cannot create credentials from config.")


HOOK_TIMEOUT = 180
STATE_FILE = "salesforce_refresh_token.json"


def state_path():
    """$XDG_DATA_HOME/autoidm/<app>/salesforce_refresh_token.json, or the platform default.

    <app> is the Meltano project folder, which is the pdt app folder.
    """
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    app = Path(os.environ.get("MELTANO_PROJECT_ROOT") or os.getcwd()).name
    return Path(base) / "autoidm" / app / STATE_FILE


def load_state_token(client_id):
    """The refresh token this tap stored for the client on its last login, or None.

    A file written for another client id (a dev and a prod org on one
    computer) is ignored rather than posted.
    """
    path = state_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        LOGGER.error("Cannot read the refresh token state at %s: %s", path, e)
        return None
    if not isinstance(data, dict) or data.get("client_id") != client_id:
        return None
    token = data.get("refresh_token") or None
    if token:
        LOGGER.info("Refresh token state at %s holds a token of length %d", path, len(token))
    return token


def store_state_token(client_id, token):
    path = state_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    handle = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(handle, json.dumps({"client_id": client_id, "refresh_token": token}).encode("utf-8"))
        os.fsync(handle)
    finally:
        os.close(handle)
    os.replace(str(tmp), str(path))
    LOGGER.info("Refresh token state at %s stored a token of length %d", path, len(token))


def run_store_hook(path, token):
    """Run the refresh-token store hook: no argv, the new token on stdin."""
    try:
        result = subprocess.run(
            [path], input=token.encode("utf-8"), capture_output=True, timeout=HOOK_TIMEOUT, check=False
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        raise Exception(f"Refresh token store hook {path} failed: {e}") from e

    output = (result.stdout + result.stderr).decode(errors="replace").strip()
    if result.returncode != 0:
        raise Exception(f"Refresh token store hook {path} failed: {output}")

    for line in output.splitlines():
        LOGGER.info("Refresh token store hook %s: %s", path, line.strip())
    LOGGER.info("Refresh token store hook %s stored a token of length %d", path, len(token))


class SalesforceAuth:
    def __init__(self, credentials, is_sandbox=False, refresh_token_store_hook=None):
        self.is_sandbox = is_sandbox
        self._credentials = credentials
        self._access_token = None
        self._instance_url = None
        self._auth_header = None
        self.login_timer = None
        self._store_hook = refresh_token_store_hook
        self._refresh_token = None

    def login(self):
        """Attempt to login and set the `instance_url` and `access_token` on success."""

    @property
    def rest_headers(self):
        return {"Authorization": f"Bearer {self._access_token}"}

    @property
    def bulk_headers(self):
        return {
            "X-SFDC-Session": self._access_token,
            "Content-Type": "application/json",
        }

    @property
    def instance_url(self):
        return self._instance_url

    @classmethod
    def from_credentials(cls, credentials, **kwargs):
        if isinstance(credentials, OAuthCredentials):
            return SalesforceAuthOAuth(credentials, **kwargs)

        if isinstance(credentials, PasswordCredentials):
            return SalesforceAuthPassword(credentials, **kwargs)

        raise Exception("Invalid credentials")


class SalesforceAuthOAuth(SalesforceAuth):
    # The minimum expiration setting for SF Refresh Tokens is 15 minutes
    REFRESH_TOKEN_EXPIRATION_PERIOD = 900

    def _login_body(self, refresh_token):
        return {
            "grant_type": "refresh_token",
            "client_id": self._credentials.client_id,
            "client_secret": self._credentials.client_secret,
            "refresh_token": refresh_token,
        }

    @property
    def _login_url(self):
        login_url = "https://login.salesforce.com/services/oauth2/token"

        if self.is_sandbox:
            login_url = "https://test.salesforce.com/services/oauth2/token"

        return login_url

    def _post_login(self, refresh_token):
        return requests.post(
            self._login_url,
            data=self._login_body(refresh_token),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    def _token_sources(self):
        """Where a refresh token can come from, most recent first.

        Each is tried once; Salesforce rejects a token the moment a newer one
        exists, so the next source is the fallback for a stale one.
        """
        client_id = self._credentials.client_id
        return [
            ("state file", lambda: load_state_token(client_id)),
            ("config", lambda: self._credentials.refresh_token),
        ]

    def _login_with_sources(self):
        tried = []
        resp = None
        for source, get in self._token_sources():
            token = get()
            if not token or token in tried:
                continue
            tried.append(token)
            self._refresh_token = token
            resp = self._post_login(token)
            if resp.status_code != 400:
                return resp
            LOGGER.warning("Salesforce rejected the refresh token from the %s; trying the next source", source)
        return resp

    def login(self):
        resp = None
        try:
            LOGGER.info("Attempting login via OAuth2")

            if self._refresh_token is None:
                resp = self._login_with_sources()
            else:
                resp = self._post_login(self._refresh_token)
            if resp is None:
                raise Exception("No refresh token is available from the state file or the config")

            resp.raise_for_status()
            auth = resp.json()

            # Salesforce has already invalidated the token we posted, so the
            # replacement must be stored before anything else can fail.
            if auth.get("refresh_token"):
                self._refresh_token = auth["refresh_token"]
                store_state_token(self._credentials.client_id, auth["refresh_token"])
                if self._store_hook:
                    run_store_hook(self._store_hook, auth["refresh_token"])

            LOGGER.info("OAuth2 login successful")
            self._access_token = auth["access_token"]
            self._instance_url = auth["instance_url"]
        except Exception as e:
            error_message = str(e)
            # A successful login's body holds the new tokens, so only a
            # rejected login's body is worth quoting.
            if resp is not None and resp.status_code >= 400:
                error_message = error_message + f", Response from Salesforce: {resp.text}"
            raise Exception(error_message) from e
        finally:
            LOGGER.info("Starting new login timer")
            self.login_timer = threading.Timer(self.REFRESH_TOKEN_EXPIRATION_PERIOD, self.login)
            self.login_timer.start()


class SalesforceAuthPassword(SalesforceAuth):
    def login(self):
        login = SalesforceLogin(sandbox=self.is_sandbox, **self._credentials._asdict())

        self._access_token, host = login
        self._instance_url = "https://" + host
