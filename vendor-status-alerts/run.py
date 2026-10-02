#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["pdt-cli[apps]==0.1.3", "meltano==4.2.2"]
# ///
"""Mail one digest of new vendor status events: Adobe, CISA, and Microsoft 365.

This folder is a complete Meltano project. Three Singer taps read the
sources into a DuckDB file, dbt turns new items into send-once
notifications, render-email builds the HTML email from
email/digest.html.j2, and target-apprise mails it. README.md describes
the Meltano jobs, how to change the email, and how to run them by hand.

Adobe and CISA are public. Microsoft 365 is read only when PDT_AZURE_TENANT_ID
is set. Mail goes out only when TARGET_APPRISE_URIS is set.

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

from pdt.config import ConfigError, check_env, find_project, load_env, merged_app
from pdt.utils import storage
from pdt.utils.log import die, log

EXIT_OK = 0
EXIT_CONFIG = 1
EXIT_INSTALL = 2
EXIT_RUN = 3

MELTANO = shutil.which("meltano", path=str(Path(sys.executable).parent)) or "meltano"


def meltano(app_dir: Path, args: list[str], run_env: dict[str, str] | None = None) -> int:
    child_env = dict(os.environ)
    if run_env:
        child_env.update(run_env)
    log("info", "starting meltano", args=" ".join(args))
    finished = subprocess.run([MELTANO, *args], cwd=app_dir, env=child_env, check=False)
    return finished.returncode


def lookback_days(cfg: dict) -> int:
    raw = str(cfg.get("notify_lookback_days", "") or "").strip()
    if not raw.isdigit() or int(raw) < 1:
        die(EXIT_CONFIG, "config.yml value must be a whole number of days, 1 or more", key="notify_lookback_days", value=raw)
    return int(raw)


def adobe_products(cfg: dict) -> str:
    names = cfg.get("adobe_products") or []
    if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
        die(EXIT_CONFIG, "config.yml value must be a list of Adobe product or cloud names", key="adobe_products")
    return "|".join(n.strip() for n in names if n.strip())


def main() -> int:
    install_only = "--install-only" in sys.argv[1:]
    app_dir = Path(__file__).resolve().parent

    # The Dockerfile runs `--install-only` at image build time, so a
    # deployed job starts with every plugin installed.
    if install_only:
        code = meltano(app_dir, ["install"])
        if code != 0:
            die(EXIT_INSTALL, "meltano install failed", exit_code=code)
        return EXIT_OK

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
    problems = check_env(app["env"])
    if problems:
        die(EXIT_CONFIG, "env vars missing", problems="; ".join(problems))
    cfg = app["config"]

    run_parent = app_dir / ".pdt" / "runs"
    run_parent.mkdir(parents=True, exist_ok=True)
    state_dir = Path(tempfile.mkdtemp(prefix="run-", dir=run_parent)) / "state"
    state_dir.mkdir()
    run_env = {
        "DUCKDB_PATH": str(state_dir / "vendor_status.duckdb"),
        "NOTIFY_LOOKBACK_DAYS": str(lookback_days(cfg)),
        "ADOBE_PRODUCTS": adobe_products(cfg),
    }
    key_path = os.environ.get("PDT_AZURE_PRIVATE_KEY_PATH", "").strip()
    if key_path != "":
        run_env["PDT_AZURE_PRIVATE_KEY_PATH"] = str(find_project() / key_path)

    sources = ["extract-adobe", "extract-cisa"]
    if os.environ.get("PDT_AZURE_TENANT_ID", "").strip() != "":
        sources.append("extract-microsoft")
    else:
        log("info", "Microsoft 365 skipped: PDT_AZURE_TENANT_ID is not set")
    notify = os.environ.get("TARGET_APPRISE_URIS", "").strip() not in ("", "[]")

    store = storage.store()
    lease = store.pull("state/", state_dir)
    failed = []
    # One failing source does not hold back the news from the others.
    for job in sources:
        if meltano(app_dir, ["run", "--force", job], run_env) != 0:
            failed.append(job)
    for job in ["transform"] + (["notify"] if notify else []):
        if meltano(app_dir, ["run", "--force", job], run_env) != 0:
            failed.append(job)
            break
    # Push state after a failure too, so the state lock is released for the next run.
    store.push(state_dir, "state/", lease)

    if not notify:
        log("info", "no mail sent: TARGET_APPRISE_URIS is not set")
    if failed:
        die(EXIT_RUN, "meltano jobs failed", jobs=", ".join(failed))
    log("info", "vendor status run complete", sources=", ".join(sources), notified=notify)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
