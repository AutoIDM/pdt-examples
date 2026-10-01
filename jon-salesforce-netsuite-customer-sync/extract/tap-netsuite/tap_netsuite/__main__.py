"""NetSuite entry point."""

from __future__ import annotations

from tap_netsuite.tap import TapNetSuite

TapNetSuite.cli()
