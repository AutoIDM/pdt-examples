"""NetSuite Authentication."""

from __future__ import annotations

import datetime
import pathlib
import typing

import jwt
import pytz
from singer_sdk.authenticators import OAuthAuthenticator

import target_netsuite.autoidm as aidm

if typing.TYPE_CHECKING:
    import logging

    from target_netsuite.target import NetSuiteSink


class NetSuiteAuthenticator(OAuthAuthenticator, aidm.AutoIDMAuthenticator):
    """Authenticator class for NetSuite."""

    def __init__(self, sink: NetSuiteSink) -> None:
        self.url_base = sink.url_base
        self._config: dict[str, typing.Any] = dict(sink.config)
        self._auth_headers: dict[str, typing.Any] = {}
        self._auth_params: dict[str, typing.Any] = {}
        self.logger: logging.Logger = sink.logger
        self._auth_endpoint = f"{sink.url_base}/auth/oauth2/v1/token"
        self._default_expiration = 3600
        self._oauth_scopes = None
        self._oauth_headers = {}
        self.access_token: str | None = None
        self.refresh_token: str | None = None
        self.last_refreshed: datetime.datetime | None = None
        self.expires_in: int | None = None

    @property
    def private_key(self) -> str | None:
        """This allows the user to supply either a file path or a direct certificate."""
        private_key_as_path = pathlib.Path(self.config["private_key"])
        if private_key_as_path.is_file():
            with private_key_as_path.open("rb") as f:
                return f.read()
        else:
            return self.config["private_key"]

    @property
    def oauth_request_body(self) -> dict:
        return {
            "grant_type": "client_credentials",
            "client_assertion_type": (
                "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
            ),
            "client_assertion": self.generate_jwt(),
        }

    def generate_jwt(self) -> str:
        payload = {
            "iss": self.config["client_id"],
            "scope": "restlets,rest_webservices,suite_analytics",
            "aud": f"https://{self.config['account_id']}.suitetalk.api.netsuite.com/services/rest/auth/oauth2/v1/token",
            "exp": datetime.datetime.now(tz=pytz.utc) + datetime.timedelta(hours=1),
            "iat": datetime.datetime.now(tz=pytz.utc),
        }
        headers = {"kid": self.config["certificate_id"]}
        return jwt.encode(
            payload=payload,
            key=self.private_key,
            algorithm="ES256",
            headers=headers,
        )
