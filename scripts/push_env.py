#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["python-dotenv", "pyyaml"]
# ///
"""Copy an app's .env values to this project's GitLab CI/CD variables.

    uv run scripts/push_env.py <app>

Copies every key that <app>/config.yml lists under env: and that has a value
in <app>/.env. It prints key names only, never a value. It needs glab signed
in with Maintainer access to autoidm/pdt-examples.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml
from dotenv import dotenv_values

PROJECT = "autoidm/pdt-examples"
ROOT = Path(__file__).resolve().parent.parent


def app_keys(app: Path) -> list[str]:
    env = (yaml.safe_load((app / "config.yml").read_text()) or {}).get("env") or {}
    keys = [*env.get("required", []), *env.get("optional", [])]
    keys += [key for group in env.get("one_of", []) for key in group]
    return keys


def glab_variable(verb: str, key: str, value: str) -> subprocess.CompletedProcess:
    # GitLab masks a value of 8 or more characters with no whitespace.
    masked = ["--masked"] if len(value) >= 8 and not any(c.isspace() for c in value) else []
    return subprocess.run(["glab", "variable", verb, key, "--raw", *masked, "-R", PROJECT],
                          input=value, capture_output=True, text=True)


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 1
    app = ROOT / argv[0]
    values = dotenv_values(app / ".env")
    copied = 0
    for key in app_keys(app):
        value = values.get(key)
        if not value:
            continue
        proc = glab_variable("set", key, value)
        if proc.returncode != 0:
            proc = glab_variable("update", key, value)
        if proc.returncode != 0:
            print(f"error: could not set {key}: {proc.stderr.strip()}")
            return 1
        print(f"set {key}")
        copied += 1
    print(f"copied {copied} variable(s) from {app.name}/.env to {PROJECT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
