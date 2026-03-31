#!/usr/bin/env python3
"""Migration 00000005: Replace Calibre feeder/watch with calibre-simple-watch."""

from __future__ import annotations

import shutil
import subprocess
import tarfile
import time
from pathlib import Path

from migrations_common import log, require_root

MIGRATION_ID = "00000005"

OLD_FEEDER_SERVICE = Path("/etc/systemd/system/calibre-feeder.service")
OLD_FEEDER_TIMER = Path("/etc/systemd/system/calibre-feeder.timer")
OLD_WATCHER_SERVICE = Path("/etc/systemd/system/calibre-watch.service")
OLD_DAEMON_SCRIPT = Path("/usr/local/sbin/calibreHelperDaemon.sh")
OLD_TRACKING_DIR = Path("/var/lib/calibre-feeder")
NEW_WATCHER_SERVICE = Path("/etc/systemd/system/calibre-simple-watch.service")
NEW_WATCHER_SCRIPT = Path("/usr/local/sbin/calibreSimpleWatcher.sh")

WATCHER_BODY = r"""#!/bin/bash

WATCH_DIR="/mnt/nas/books/upload"
LIBRARY_PATH="/mnt/nas/books"

mkdir -p "$WATCH_DIR"

inotifywait -m "$WATCH_DIR" -e create -e moved_to --format '%w%f' |
  while read filepath; do
    if [[ "$filepath" =~ \.(pdf|epub|mobi|azw|azw3)$ ]]; then
      echo "[$(date)] Processing: $(basename "$filepath")"
      if calibredb add "$filepath" --library-path="$LIBRARY_PATH" 2>&1; then
        echo "[$(date)] Added and removing: $(basename "$filepath")"
        rm -f "$filepath"
      else
        echo "[$(date)] Duplicate or failed, removing: $(basename "$filepath")"
        rm -f "$filepath"
      fi
    fi
  done
"""

SERVICE_BODY = """[Unit]
Description=Calibre Simple Watch Directory Monitor
After=network.target calibre-web.service
Wants=calibre-web.service

[Service]
Type=simple
User=calibre
Group=calibre
ExecStart=/usr/local/sbin/calibreSimpleWatcher.sh
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""


def _run(cmd: list[str], check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check)


def main() -> int:
    require_root()
    log(MIGRATION_ID, "Calibre System Simplification")

    calibre_web = Path("/etc/systemd/system/calibre-web.service")
    if not calibre_web.is_file():
        log(MIGRATION_ID, "Calibre Web not installed; nothing to do")
        return 0

    old_exists = any(
        p.is_file() for p in (OLD_FEEDER_SERVICE, OLD_WATCHER_SERVICE, OLD_DAEMON_SCRIPT)
    )

    if NEW_WATCHER_SERVICE.is_file() and _run(
        ["systemctl", "is-enabled", "--quiet", "calibre-simple-watch.service"]
    ).returncode == 0:
        if not OLD_FEEDER_SERVICE.is_file() and not OLD_WATCHER_SERVICE.is_file():
            log(MIGRATION_ID, "Migration already completed")
            return 0

    if not old_exists and not NEW_WATCHER_SERVICE.is_file():
        log(MIGRATION_ID, "Neither old nor new system; fresh install path")
        return 0

    for svc in ("calibre-feeder.service", "calibre-feeder.timer", "calibre-watch.service"):
        _run(["systemctl", "stop", svc], check=False)
    for svc in ("calibre-feeder.service", "calibre-feeder.timer", "calibre-watch.service"):
        _run(["systemctl", "disable", svc], check=False)

    for p in (OLD_FEEDER_SERVICE, OLD_FEEDER_TIMER, OLD_WATCHER_SERVICE):
        p.unlink(missing_ok=True)

    for p in (
        Path("/etc/systemd/system/calibre-feeder.version"),
        Path("/etc/systemd/system/calibre-watch.version"),
    ):
        p.unlink(missing_ok=True)

    if OLD_TRACKING_DIR.is_dir():
        archive = Path(f"/var/log/homeserver/calibre-feeder-archive-{int(time.time())}.tar.gz")
        archive.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive, "w:gz") as tf:
            tf.add(str(OLD_TRACKING_DIR), arcname=OLD_TRACKING_DIR.name)
        shutil.rmtree(OLD_TRACKING_DIR)

    _run(["systemctl", "daemon-reload"], check=False)

    if shutil.which("inotifywait") is None:
        _run(["apt-get", "update", "-qq"], check=False)
        if _run(["apt-get", "install", "-qq", "-y", "inotify-tools"]).returncode != 0:
            log(MIGRATION_ID, "Failed to install inotify-tools", level="ERROR")
            return 1

    if shutil.which("calibredb") is None:
        _run(["apt-get", "update", "-qq"], check=False)
        if _run(["apt-get", "install", "-qq", "-y", "calibre-bin"]).returncode != 0:
            log(MIGRATION_ID, "Failed to install calibre-bin", level="ERROR")
            return 1

    NEW_WATCHER_SCRIPT.write_text(WATCHER_BODY, encoding="utf-8")
    NEW_WATCHER_SCRIPT.chmod(0o755)

    NEW_WATCHER_SERVICE.write_text(SERVICE_BODY, encoding="utf-8")
    NEW_WATCHER_SERVICE.chmod(0o644)

    upload = Path("/mnt/nas/books/upload")
    upload.mkdir(parents=True, exist_ok=True)
    try:
        shutil.chown(upload, user="calibre", group="calibre")
        upload.chmod(0o775)
    except OSError:
        log(MIGRATION_ID, "WARNING: could not chown/chmod upload directory", level="WARNING")

    _run(["systemctl", "daemon-reload"], check=False)
    if _run(["systemctl", "enable", "calibre-simple-watch.service"]).returncode != 0:
        log(MIGRATION_ID, "Failed to enable calibre-simple-watch", level="ERROR")
        return 1
    _run(["systemctl", "start", "calibre-simple-watch.service"], check=False)
    time.sleep(3)

    log(MIGRATION_ID, "SUCCESS: Calibre simple watcher installed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
