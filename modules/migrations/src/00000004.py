#!/usr/bin/env python3
"""Migration 00000004: Remove NAS dependency from filebrowser.service."""

from __future__ import annotations

import re
import shutil
import subprocess
import time
from pathlib import Path

from migrations_common import log, require_root

MIGRATION_ID = "00000004"
SERVICE_FILE = Path("/etc/systemd/system/filebrowser.service")

DESIRED = """[Unit]
Description=File Browser
After=network.target 

[Service]
Type=simple
User=filebrowser
Group=filebrowser
ExecStart=/usr/local/bin/filebrowser -d /etc/filebrowser/filebrowser.db
WorkingDirectory=/etc/filebrowser
Restart=on-failure
RestartSec=5
StartLimitInterval=60s
StartLimitBurst=3

[Install]
WantedBy=multi-user.target
"""


def main() -> int:
    require_root()
    log(MIGRATION_ID, "Filebrowser Service Fix")

    if not SERVICE_FILE.is_file():
        log(MIGRATION_ID, "Filebrowser not installed; nothing to do")
        return 0

    if SERVICE_FILE.read_text(encoding="utf-8") == DESIRED:
        log(MIGRATION_ID, "Service already matches desired state")
        return 0

    backup = Path(f"{SERVICE_FILE}.pre-migration-{int(time.time())}")
    shutil.copy2(SERVICE_FILE, backup)
    SERVICE_FILE.write_text(DESIRED, encoding="utf-8")

    if re.search(r"ExecStartPre=.*test.*mnt/nas", SERVICE_FILE.read_text()):
        log(MIGRATION_ID, "ERROR: NAS dependency still present", level="ERROR")
        shutil.copy2(backup, SERVICE_FILE)
        return 1

    subprocess.run(["systemd-analyze", "verify", str(SERVICE_FILE)], check=False)
    subprocess.run(["systemctl", "daemon-reload"], check=False)

    if subprocess.run(["systemctl", "is-active", "--quiet", "filebrowser.service"], check=False).returncode == 0:
        subprocess.run(["systemctl", "restart", "filebrowser.service"], check=False)
        time.sleep(3)

    log(MIGRATION_ID, "SUCCESS: filebrowser.service updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
