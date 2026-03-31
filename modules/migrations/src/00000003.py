#!/usr/bin/env python3
"""Migration 00000003: mountNas.service with vault dependencies."""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from migrations_common import log, require_root

MIGRATION_ID = "00000003"
SERVICE_FILE = Path("/etc/systemd/system/mountNas.service")

DESIRED = """[Unit]
Description=NAS Mount Status
ConditionPathExists=/vault/scripts/init.sh
ConditionPathIsMountPoint=/vault
Requires=vault.mount
After=vault.mount

[Service]
Type=oneshot
ExecStart=/vault/scripts/init.sh
StandardOutput=journal
StandardError=journal
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
"""


def main() -> int:
    require_root()
    log(MIGRATION_ID, "Mount NAS Service Update")

    if SERVICE_FILE.is_file() and SERVICE_FILE.read_text(encoding="utf-8") == DESIRED:
        log(MIGRATION_ID, "Service file already matches desired state")
        return 0

    if subprocess.run(["systemctl", "is-active", "--quiet", "mountNas.service"], check=False).returncode == 0:
        subprocess.run(["systemctl", "stop", "mountNas.service"], check=False)

    backup = Path(f"{SERVICE_FILE}.pre-migration-{int(time.time())}")
    if SERVICE_FILE.is_file():
        shutil.copy2(SERVICE_FILE, backup)
        log(MIGRATION_ID, f"Backup: {backup}")

    SERVICE_FILE.write_text(DESIRED, encoding="utf-8")
    SERVICE_FILE.chmod(0o644)

    subprocess.run(["systemd-analyze", "verify", str(SERVICE_FILE)], check=False)
    subprocess.run(["systemctl", "daemon-reload"], check=False)
    log(MIGRATION_ID, "SUCCESS: mountNas.service updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
