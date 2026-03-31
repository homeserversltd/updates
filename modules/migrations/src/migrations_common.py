"""Shared helpers for HOMESERVER numbered migrations (Python only)."""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

MIGRATION_LOG = Path("/var/log/homeserver/migrations.log")


def log(prefix: str, message: str, *, level: str = "INFO") -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {prefix}: {message}"
    print(line, file=sys.stderr if level == "ERROR" else sys.stdout)
    try:
        MIGRATION_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(MIGRATION_LOG, "a", encoding="utf-8") as fh:
            fh.write(f"[{ts}] [{level}] {prefix}: {message}\n")
    except OSError:
        pass


def require_root() -> None:
    if os.geteuid() != 0:
        log("migration", "ERROR: must run as root", level="ERROR")
        raise SystemExit(1)
