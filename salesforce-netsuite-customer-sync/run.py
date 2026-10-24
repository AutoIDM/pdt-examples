#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["pdt-cli[apps]==0.1.2", "meltano==4.2.2"]
# ///
"""Copy Salesforce accounts and contacts into NetSuite customers and contacts.

This folder is a complete Meltano project. tap-salesforce reads Account and
Contact, target-duckdb stages them, dbt and autoidm-transform build the
desired NetSuite state, and target-netsuite writes the difference back.
README.md describes the four Meltano jobs and how to run them by hand.

Needs a Salesforce user with API access, a NetSuite integration record with
REST Web Services and OAuth 2.0 client credentials, and a DuckDB file
for the staging tables.

Credentials come from .env at this folder or any parent. config.yml lists
the names, and env.template describes each one.

Exit codes: 0 ok, 1 bad config, 2 meltano install failure, 3 meltano run
failure.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from pdt.config import ConfigError, check_env, load_env, merged_app
from pdt.utils import storage
from pdt.utils.log import die, log

EXIT_OK = 0
EXIT_CONFIG = 1
EXIT_INSTALL = 2
EXIT_RUN = 3

MELTANO = shutil.which("meltano", path=str(Path(sys.executable).parent)) or "meltano"
INSTALL_ARGS = ["install"]
RUN_ARGS = ["run", "--force", "extract", "transform", "artifacts"]
LOAD_ARGS = ["run", "--force", "load"]


def meltano(app_dir: Path, args: list[str], environment: str, run_env: dict[str, str] | None = None) -> int:
    child_env = dict(os.environ)
    child_env["MELTANO_ENVIRONMENT"] = environment
    if run_env:
        child_env.update(run_env)
    log("info", "starting meltano", args=" ".join(args), environment=environment)
    finished = subprocess.run([MELTANO, *args], cwd=app_dir, env=child_env, check=False)
    return finished.returncode


def main() -> int:
    install_only = "--install-only" in sys.argv[1:]
    app_dir = Path(__file__).resolve().parent

    if not install_only:
        try:
            env_files = load_env(app_dir)
        except ConfigError as e:
            die(EXIT_CONFIG, "bad env", error=str(e))
        for path in env_files:
            log("info", "loaded env file", path=str(path))

    try:
        app = merged_app(app_dir.name)
    except ConfigError as e:
        die(EXIT_CONFIG, "config error", error=str(e))
    problems = [] if install_only else check_env(app["env"])
    if problems:
        die(EXIT_CONFIG, "env vars missing", problems="; ".join(problems))
    environment = str(app["config"].get("meltano_environment", "") or "").strip()
    if environment == "":
        die(EXIT_CONFIG, "config.yml missing key", key="meltano_environment")

    # The Dockerfile runs `--install-only` at image build time, so a
    # deployed job starts with every plugin installed.
    if install_only:
        code = meltano(app_dir, INSTALL_ARGS, environment)
        if code != 0:
            die(EXIT_INSTALL, "meltano install failed", exit_code=code)
        return EXIT_OK

    # One fresh local folder per run. state/ is pulled from the PDT Store
    # under a lock, output/ collects the CSV artifacts for this run.
    store = storage.store()
    run_dir = app_dir / ".pdt" / "runs" / storage.RUN_ID
    state_dir = run_dir / "state"
    output_dir = run_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        lease = store.pull("state/", state_dir)
    except storage.StorageLocked as e:
        die(EXIT_RUN, "state locked", error=str(e))
    log("info", "pulled state", store=store.url, local=str(state_dir))

    def abort(message: str, code: int) -> None:
        # The store has no abort call, so release the lock by hand. Without
        # this a failed run blocks the next one until the lock's TTL passes.
        if lease.lock:
            store.backend().delete(storage.LOCK)
        die(EXIT_RUN, message, exit_code=code)

    run_env = {
        "DUCKDB_PATH": str(state_dir / "sync.duckdb"),
        "ARTIFACTS_PATH": str(output_dir) + os.sep,
        # tap-salesforce rotates its refresh token, so the store must survive the run.
        "SALESFORCE_REFRESH_TOKEN_STORE_DIR": str(state_dir),
    }
    code = meltano(app_dir, RUN_ARGS, environment, run_env)
    if code != 0:
        abort("meltano run failed", code)

    # Artifacts go up before the load, so a person can review them even
    # when NetSuite rejects the writes.
    artifacts = store.run_folder() + "artifacts/"
    store.push(output_dir, artifacts)
    log("info", "pushed artifacts", remote=artifacts)

    code = meltano(app_dir, LOAD_ARGS, environment, run_env)
    if code != 0:
        abort("meltano load failed", code)

    # A successful load is the only thing that advances the shared state.
    # This also releases the lock the pull took.
    store.push(state_dir, "state/", lease)
    log("info", "pushed state", remote="state/")

    log("info", "sync complete", environment=environment)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
