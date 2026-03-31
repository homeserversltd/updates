#!/usr/bin/env python3
"""Migration 00000002: Ensure /etc/homeserver.factory exists (immutable factory backup)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from migrations_common import log, require_root

MIGRATION_ID = "00000002"
FACTORY_CONFIG = Path("/etc/homeserver.factory")
SOURCE_CANDIDATES = [
    Path("/var/www/homeserver/src/config/homeserver.json"),
    Path("/var/www/homeserver/src/config/homeserver.factory"),
    Path("/etc/homeserver.json"),
]


def _valid_json(path: Path) -> bool:
    try:
        json.loads(path.read_text(encoding="utf-8"))
        return True
    except (OSError, json.JSONDecodeError):
        return False


def main() -> int:
    require_root()
    log(MIGRATION_ID, "Factory Config Creation")

    if FACTORY_CONFIG.is_file() and _valid_json(FACTORY_CONFIG):
        log(MIGRATION_ID, f"Factory config already valid: {FACTORY_CONFIG}")
        return 0

    source: Path | None = None
    for p in SOURCE_CANDIDATES:
        if p.is_file():
            source = p
            log(MIGRATION_ID, f"Using source config: {p}")
            break
    if source is None:
        log(MIGRATION_ID, "No source configuration file found", level="ERROR")
        return 1

    if FACTORY_CONFIG.is_file():
        subprocess.run(["chattr", "-i", str(FACTORY_CONFIG)], check=False)
        FACTORY_CONFIG.unlink(missing_ok=True)

    shutil.copy2(source, FACTORY_CONFIG)
    FACTORY_CONFIG.chmod(0o444)
    shutil.chown(FACTORY_CONFIG, user="root", group="root")
    subprocess.run(["chattr", "+i", str(FACTORY_CONFIG)], check=False)

    if not _valid_json(FACTORY_CONFIG):
        log(MIGRATION_ID, "Factory config is not valid JSON after creation", level="ERROR")
        return 1

    log(MIGRATION_ID, "SUCCESS: factory config created and verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
