#!/usr/bin/env python3
"""tap-salesforce refresh_token_store_hook: writes a GitLab CI/CD project variable.

Keeps a copy of the rotating token in a GitLab CI/CD project variable, so a
pipeline whose state is gone starts from the current token. No argv; the
tap sends the new token on stdin with no trailing newline.

Reads GITLAB_TOKEN, CI_PROJECT_ID, CI_API_V4_URL, GITLAB_VARIABLE_KEY, and
GITLAB_VARIABLE_ENVIRONMENT_SCOPE from the environment. GITLAB_TOKEN must be
a project or group access token with the `api` scope; the pipeline's own
CI_JOB_TOKEN cannot read or write variables.
"""

import os
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_API_URL = "https://gitlab.com/api/v4"
DEFAULT_VARIABLE_KEY = "TAP_SALESFORCE_REFRESH_TOKEN"


def read_config():
    token = os.environ.get("GITLAB_TOKEN")
    project_id = os.environ.get("CI_PROJECT_ID")
    if not token or not project_id:
        print("GITLAB_TOKEN and CI_PROJECT_ID are required", file=sys.stderr)
        sys.exit(2)

    return {
        "token": token,
        "api_url": os.environ.get("CI_API_V4_URL", DEFAULT_API_URL).rstrip("/"),
        "project_id": project_id,
        "key": os.environ.get("GITLAB_VARIABLE_KEY", DEFAULT_VARIABLE_KEY),
        "environment_scope": os.environ.get("GITLAB_VARIABLE_ENVIRONMENT_SCOPE"),
    }


def variable_url(config):
    key = urllib.parse.quote(config["key"], safe="")
    url = f"{config['api_url']}/projects/{config['project_id']}/variables/{key}"
    if config["environment_scope"]:
        url += "?" + urllib.parse.urlencode({"filter[environment_scope]": config["environment_scope"]})
    return url


def variables_url(config):
    return f"{config['api_url']}/projects/{config['project_id']}/variables"


def request(url, config, method="GET", form=None):
    data = urllib.parse.urlencode(form).encode("ascii") if form is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("PRIVATE-TOKEN", config["token"])
    return req


def _put(config, token):
    req = request(variable_url(config), config, method="PUT", form={"value": token})
    try:
        with urllib.request.urlopen(req):
            return True
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        print(f"GitLab PUT variable failed: {e.code} {e.reason}", file=sys.stderr)
        sys.exit(1)


def _post(config, token):
    form = {"key": config["key"], "value": token, "masked": "true"}
    if config["environment_scope"]:
        form["environment_scope"] = config["environment_scope"]
    req = request(variables_url(config), config, method="POST", form=form)
    try:
        with urllib.request.urlopen(req):
            return 0
    except urllib.error.HTTPError as e:
        print(f"GitLab POST variable failed: {e.code} {e.reason}", file=sys.stderr)
        return 1


def main(argv):
    token = sys.stdin.read().strip()
    if not token:
        print("refusing to store an empty refresh token", file=sys.stderr)
        return 2

    config = read_config()
    if _put(config, token):
        return 0
    return _post(config, token)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
