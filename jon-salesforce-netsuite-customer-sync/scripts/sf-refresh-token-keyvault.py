#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["pdt-cli[apps]==0.1.2"]
# ///
"""tap-salesforce refresh_token_store_hook: writes the token into the app's pdt secret.

Sets TAP_SALESFORCE_REFRESH_TOKEN in the deployed app's secret (the Key
Vault secret on Azure, Secrets Manager on AWS, Secret Manager on Google
Cloud), or in the nearest .env file when the app runs on this computer.
The tap's own state file is the copy it reads first; this one is the
copy a run with no state starts from, and the one `pdt secrets` shows. No
argv; the tap sends the new token on stdin with no trailing newline.
"""

from __future__ import annotations

import sys

from pdt.utils import env_secret


def main() -> int:
    token = sys.stdin.read().strip()
    if not token:
        print("refusing to store an empty refresh token", file=sys.stderr)
        return 2
    env_secret.update("TAP_SALESFORCE_REFRESH_TOKEN", token)
    return 0


if __name__ == "__main__":
    sys.exit(main())
