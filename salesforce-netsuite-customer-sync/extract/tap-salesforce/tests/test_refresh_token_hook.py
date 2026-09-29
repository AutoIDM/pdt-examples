import json
import stat
import tempfile
import threading
from pathlib import Path

import pytest

from tap_salesforce.salesforce.credentials import (
    OAuthCredentials,
    SalesforceAuthOAuth,
    load_state_token,
    state_path,
)

APP_DIR = Path(__file__).resolve().parents[3]


class FakeResponse:
    def __init__(self, status_code=200, refresh_token="tok1"):
        self.status_code = status_code
        self._refresh_token = refresh_token

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")

    def json(self):
        return {"access_token": "a", "instance_url": "https://x", "refresh_token": self._refresh_token}

    @property
    def text(self):
        return "response body"


def _write_hook(path, body):
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


STORE_HOOK_BODY = """#!/bin/sh
cat > "{store}"
"""


def _make_store_hook(tmp_path):
    store_file = tmp_path / "store.txt"
    store_hook = tmp_path / "store.sh"
    _write_hook(store_hook, STORE_HOOK_BODY.format(store=store_file))
    return store_hook, store_file


def _make_auth(refresh_token_store_hook, config_token="tok0", client_id="cid"):
    creds = OAuthCredentials(client_id, "csecret", config_token)
    return SalesforceAuthOAuth(creds, refresh_token_store_hook=refresh_token_store_hook)


@pytest.fixture(autouse=True)
def _own_state_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "xdg"))
    monkeypatch.setenv("MELTANO_PROJECT_ROOT", str(APP_DIR))
    return tmp_path / "xdg"


@pytest.fixture(autouse=True)
def _cancel_timers():
    timers = []
    yield timers
    for t in timers:
        t.cancel()
    for thread in threading.enumerate():
        if isinstance(thread, threading.Timer):
            thread.cancel()


def test_first_login_uses_configured_token_then_rotated_token_lands_in_hook(_cancel_timers):
    with tempfile.TemporaryDirectory() as tmp_dir:
        store_hook, store_file = _make_store_hook(Path(tmp_dir))
        posted = []
        auth = _make_auth(str(store_hook))
        auth._post_login = lambda refresh_token: (posted.append(refresh_token), FakeResponse())[1]

        auth.login()
        _cancel_timers.append(auth.login_timer)

        assert posted == ["tok0"]
        assert store_file.read_text() == "tok1"


def test_hook_store_failure_raises(_cancel_timers):
    with tempfile.TemporaryDirectory() as tmp_dir:
        store_hook = Path(tmp_dir) / "store.sh"
        _write_hook(store_hook, "#!/bin/sh\nexit 1\n")

        auth = _make_auth(str(store_hook))
        auth._post_login = lambda refresh_token: FakeResponse()

        with pytest.raises(Exception) as failure:
            auth.login()
        _cancel_timers.append(auth.login_timer)
        assert "response body" not in str(failure.value)


def test_no_hook_configured(_cancel_timers):
    auth = _make_auth(None)
    auth._post_login = lambda refresh_token: FakeResponse()

    auth.login()
    _cancel_timers.append(auth.login_timer)

    assert auth._access_token == "a"


def test_every_login_writes_the_state_file(_cancel_timers, _own_state_dir):
    auth = _make_auth(None)
    auth._post_login = lambda refresh_token: FakeResponse(refresh_token="tok1")

    auth.login()
    _cancel_timers.append(auth.login_timer)

    path = state_path()
    assert path == _own_state_dir / "autoidm" / APP_DIR.name / "salesforce_refresh_token.json"
    assert json.loads(path.read_text()) == {"client_id": "cid", "refresh_token": "tok1"}
    assert oct(path.stat().st_mode & 0o777) == "0o600"
    assert load_state_token("cid") == "tok1"


def test_the_state_file_is_tried_before_the_config(_cancel_timers):
    auth = _make_auth(None)
    auth._post_login = lambda refresh_token: FakeResponse(refresh_token="tok1")
    auth.login()
    _cancel_timers.append(auth.login_timer)

    posted = []
    auth = _make_auth(None)
    auth._post_login = lambda refresh_token: (posted.append(refresh_token), FakeResponse(refresh_token="tok2"))[1]

    auth.login()
    _cancel_timers.append(auth.login_timer)

    assert posted == ["tok1"]
    assert load_state_token("cid") == "tok2"


def test_a_rejected_state_token_falls_back_to_the_config(_cancel_timers):
    auth = _make_auth(None)
    auth._post_login = lambda refresh_token: FakeResponse(refresh_token="tok-stale")
    auth.login()
    _cancel_timers.append(auth.login_timer)

    posted = []
    auth = _make_auth(None)
    auth._post_login = lambda refresh_token: (
        posted.append(refresh_token),
        FakeResponse(status_code=400 if refresh_token != "tok0" else 200, refresh_token="tok3"),
    )[1]

    auth.login()
    _cancel_timers.append(auth.login_timer)

    assert posted == ["tok-stale", "tok0"]
    assert load_state_token("cid") == "tok3"


def test_a_state_file_for_another_client_id_is_ignored(_cancel_timers):
    auth = _make_auth(None, client_id="cid-dev")
    auth._post_login = lambda refresh_token: FakeResponse(refresh_token="tok-dev")
    auth.login()
    _cancel_timers.append(auth.login_timer)

    posted = []
    auth = _make_auth(None, client_id="cid-prod")
    auth._post_login = lambda refresh_token: (posted.append(refresh_token), FakeResponse(refresh_token="tok-prod"))[1]

    auth.login()
    _cancel_timers.append(auth.login_timer)

    assert posted == ["tok0"]
    assert load_state_token("cid-prod") == "tok-prod"
    assert load_state_token("cid-dev") is None


def test_a_token_seen_twice_is_posted_once(_cancel_timers):
    posted = []
    auth = _make_auth(None, config_token="tok0")
    auth._post_login = lambda refresh_token: (posted.append(refresh_token), FakeResponse(refresh_token=None))[1]
    state_path().parent.mkdir(parents=True)
    state_path().write_text(json.dumps({"client_id": "cid", "refresh_token": "tok0"}))

    auth.login()
    _cancel_timers.append(auth.login_timer)

    assert posted == ["tok0"]
