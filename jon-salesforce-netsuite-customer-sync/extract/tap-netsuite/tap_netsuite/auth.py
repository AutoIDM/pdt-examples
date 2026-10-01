"""NetSuite Authentication."""

from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
import pathlib
import random
import time
import typing
import urllib.parse

import jwt
import pytz
from singer_sdk.authenticators import OAuthAuthenticator, SingletonMeta

if typing.TYPE_CHECKING:
    from tap_netsuite.rest_client import NetSuiteRESTStream


# The SingletonMeta metaclass makes your streams reuse the same authenticator instance.
# If this behaviour interferes with your use-case, you can remove the metaclass.
class NetSuiteRESTAuthenticator(OAuthAuthenticator, metaclass=SingletonMeta):
    """Authenticator class for NetSuite."""

    def __init__(self, stream: NetSuiteRESTStream) -> None:
        self.url_base = stream.url_base
        super().__init__(
            stream=stream,
            auth_endpoint=f"{stream.url_base}/auth/oauth2/v1/token",
            oauth_scopes=None,
            default_expiration=3600,
            oauth_headers=None,
        )

    @property
    def private_key(self) -> str | None:
        """This allows the user to supply either a file path or a direct certificate."""
        private_key_as_path = pathlib.Path(self.config["private_key"])
        if private_key_as_path.is_file():
            self.logger.info("Using `private_key` config option as file.")
            with private_key_as_path.open("rb") as f:
                return f.read()
        else:
            self.logger.info("Using `private_key` config option as raw string.")
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

    @classmethod
    def create_for_stream(cls, stream: NetSuiteRESTStream) -> NetSuiteRESTAuthenticator:
        """Instantiate an authenticator for a specific Singer stream.

        Args:
            stream: The Singer stream instance.

        Returns:
            A new authenticator.
        """
        return cls(stream=stream)


class NetsuiteSOAPPassportHandler(metaclass=SingletonMeta):

    def __init__(self, config: dict, wsdl_major_version: str) -> None:
        self.account_id = config["account_id"]
        self.consumer_key = config["soap_consumer_key"]
        self.consumer_secret = config["soap_consumer_secret"]
        self.token_id = config["soap_token_id"]
        self.token_secret = config["soap_token_secret"]
        self.wsdl_major_version = wsdl_major_version

    def generate_passport(self) -> str:
        """
        Docs:
        1. Human readable: https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_4395630653.html#bridgehead_4398049035
        2. XSD Schema: https://webservices.netsuite.com/xsd/platform/v2024_1_0/core.xsd
        """

        nonce = self._generate_nonce()
        timestamp = str(round(time.time()))
        signature = self._generate_signature(nonce, timestamp)

        return (
            f'<ns:tokenPassport xmlns:ns="urn:messages_{self.wsdl_major_version}.platform.webservices.netsuite.com">'  # noqa: E501
            f"<ns:account>{self.account_id}</ns:account>"
            f"<ns:consumerKey>{self.consumer_key}</ns:consumerKey>"
            f"<ns:token>{self.token_id}</ns:token>"
            f"<ns:nonce>{nonce}</ns:nonce>"
            f"<ns:timestamp>{timestamp}</ns:timestamp>"
            f'<ns:signature algorithm="HMAC_SHA256">{signature}</ns:signature>'
            "</ns:tokenPassport>"
        )

    def _generate_nonce(self) -> str:
        """
        64 is the maximum nonce length.
        Docs: https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_4395630653.html#bridgehead_4398049035
        """
        return "".join(
            random.choices("abcdefghijklmnopqrstuvwxyz1234567890", k=64)  # noqa: S311
        )

    def _generate_signature(self, nonce: str, timestamp: str) -> str:
        """
        Docs: https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_1534941088.html#subsect_1520523663
        """

        base_string = (
            f"{urllib.parse.quote_plus(self.account_id)}&"
            f"{urllib.parse.quote_plus(self.consumer_key)}&"
            f"{urllib.parse.quote_plus(self.token_id)}&"
            f"{urllib.parse.quote_plus(nonce)}&"
            f"{urllib.parse.quote_plus(timestamp)}"
        )

        signature_key = (
            f"{urllib.parse.quote_plus(self.consumer_secret)}&"
            f"{urllib.parse.quote_plus(self.token_secret)}"
        )

        hmac_obj = hmac.new(
            signature_key.encode(), base_string.encode(), hashlib.sha256
        )
        return base64.b64encode(hmac_obj.digest()).decode()
