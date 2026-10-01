import http.server
import json
import os
import subprocess
import sys
import threading
import urllib.parse
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
KEYVAULT_STORE = SCRIPTS_DIR / "sf-refresh-token-keyvault.py"
GITLAB_STORE = SCRIPTS_DIR / "sf-refresh-token-gitlab.py"

DEFAULT_KEY = "TAP_SALESFORCE_REFRESH_TOKEN"


def _run(script, env, input_text=None):
    return subprocess.run(
        [sys.executable, str(script)],
        input=input_text,
        env=env,
        capture_output=True,
        text=True,
    )


def _pdt_env(app_dir):
    return {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PDT_PROJECT": str(app_dir.parent)}


@pytest.fixture
def app_dir(tmp_path):
    pytest.importorskip("pdt.utils.env_secret")
    (tmp_path / "pdt.yml").write_text("platform:\n  provider: windows\n")
    folder = tmp_path / "app"
    folder.mkdir()
    return folder


def _run_in(script, app_dir, input_text=None):
    return subprocess.run(
        [sys.executable, str(script)],
        input=input_text,
        env=_pdt_env(app_dir),
        cwd=app_dir,
        capture_output=True,
        text=True,
    )


def test_keyvault_store_writes_the_env_file_and_keeps_the_rest(app_dir):
    (app_dir / ".env").write_text("OTHER=keep\n")
    result = _run_in(KEYVAULT_STORE, app_dir, input_text="tok-123")
    assert result.returncode == 0, result.stderr
    text = (app_dir / ".env").read_text()
    assert "TAP_SALESFORCE_REFRESH_TOKEN=tok-123" in text
    assert "OTHER=keep" in text


def test_keyvault_store_creates_the_env_file_when_none_exists(app_dir):
    result = _run_in(KEYVAULT_STORE, app_dir, input_text="tok-123")
    assert result.returncode == 0, result.stderr
    assert (app_dir / ".env").read_text().strip() == "TAP_SALESFORCE_REFRESH_TOKEN=tok-123"


def test_keyvault_store_empty_stdin_exits_2(app_dir):
    result = _run_in(KEYVAULT_STORE, app_dir, input_text="")
    assert result.returncode == 2
    assert not (app_dir / ".env").exists()


class _ScriptedHandler(http.server.BaseHTTPRequestHandler):
    script = []
    requests = []

    def _handle(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length else ""
        self.__class__.requests.append(
            {
                "method": self.command,
                "path": self.path,
                "headers": dict(self.headers),
                "body": body,
            }
        )
        status, payload = self.__class__.script.pop(0)
        self.send_response(status)
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_header("Content-Length", "0")
            self.end_headers()

    def do_GET(self):
        self._handle()

    def do_PUT(self):
        self._handle()

    def do_POST(self):
        self._handle()

    def log_message(self, *args):
        pass


@pytest.fixture
def gitlab_server():
    _ScriptedHandler.script = []
    _ScriptedHandler.requests = []
    server = http.server.HTTPServer(("127.0.0.1", 0), _ScriptedHandler)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    try:
        yield server, _ScriptedHandler
    finally:
        server.shutdown()
        thread.join()


def _gitlab_env(server, **extra):
    env = {
        "PATH": "/usr/bin:/bin",
        "GITLAB_TOKEN": "secret-token",
        "CI_API_V4_URL": f"http://127.0.0.1:{server.server_port}",
        "CI_PROJECT_ID": "42",
    }
    env.update(extra)
    return env


def test_gitlab_store_put_200_sends_value_body_and_token_header(gitlab_server):
    server, handler = gitlab_server
    handler.script = [(200, {})]

    result = _run(GITLAB_STORE, _gitlab_env(server), input_text="tok-new")
    assert result.returncode == 0
    req = handler.requests[0]
    assert req["method"] == "PUT"
    assert urllib.parse.parse_qs(req["body"]) == {"value": ["tok-new"]}
    assert req["headers"]["Private-Token"] == "secret-token"
    assert "tok-new" not in result.stdout


def test_gitlab_store_put_404_then_post_201_masked(gitlab_server):
    server, handler = gitlab_server
    handler.script = [(404, None), (201, {})]

    result = _run(GITLAB_STORE, _gitlab_env(server), input_text="tok-new")
    assert result.returncode == 0
    assert len(handler.requests) == 2
    put_req, post_req = handler.requests
    assert put_req["method"] == "PUT"
    assert post_req["method"] == "POST"
    form = urllib.parse.parse_qs(post_req["body"])
    assert form["key"] == [DEFAULT_KEY]
    assert form["value"] == ["tok-new"]
    assert form["masked"] == ["true"]


def test_gitlab_store_put_500_exits_1(gitlab_server):
    server, handler = gitlab_server
    handler.script = [(500, None)]

    result = _run(GITLAB_STORE, _gitlab_env(server), input_text="tok-new")
    assert result.returncode == 1


def test_gitlab_store_environment_scope_adds_filter_query(gitlab_server):
    server, handler = gitlab_server
    handler.script = [(200, {})]

    result = _run(
        GITLAB_STORE,
        _gitlab_env(server, GITLAB_VARIABLE_ENVIRONMENT_SCOPE="production"),
        input_text="tok-new",
    )
    assert result.returncode == 0
    parsed = urllib.parse.urlparse(handler.requests[0]["path"])
    query = urllib.parse.parse_qs(parsed.query)
    assert query["filter[environment_scope]"] == ["production"]


def test_gitlab_store_empty_stdin_exits_2(gitlab_server):
    server, handler = gitlab_server

    result = _run(GITLAB_STORE, _gitlab_env(server), input_text="")
    assert result.returncode == 2
    assert handler.requests == []
