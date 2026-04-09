#!/usr/bin/env python3
"""Migration 00000007: Apply PARTLABELs on system disk."""

from __future__ import annotations

import re
import shutil
import subprocess
import time
from pathlib import Path

from migrations_common import log, require_root

MIGRATION_ID = "00000007"
LABELS = [
    "homeserver-boot-efi",
    "homeserver-boot",
    "homeserver-swap",
    "homeserver-vault",
    "homeserver-deploy",
    "homeserver-root",
]
def _root_disk() -> tuple[str, str]:
    r = subprocess.run(
        ["findmnt", "-n", "-o", "SOURCE", "/"],
        capture_output=True,
        text=True,
        check=False,
    )
    root_source = (r.stdout or "").strip()
    if not root_source or not Path(root_source).exists():
        raise RuntimeError("Could not determine root block device")

    name = Path(root_source).name
    if re.match(r"^nvme.*p\d+$", name):
        disk = str(Path("/dev") / name.rsplit("p", 1)[0])
    else:
        disk = re.sub(r"\d+$", "", root_source)
    if not disk or not Path(disk).exists():
        raise RuntimeError(f"Could not derive disk from {root_source}")
    return root_source, disk


def _apply_partlabels(disk: str) -> None:
    if shutil.which("sgdisk") is None:
        raise RuntimeError("sgdisk not found (install gdisk)")
    for i, label in enumerate(LABELS, start=1):
        log(MIGRATION_ID, f"Setting partition {i} PARTLABEL {label}")
        r = subprocess.run(["sgdisk", "-c", f"{i}:{label}", disk], check=False)
        if r.returncode != 0:
            raise RuntimeError(f"sgdisk failed for partition {i}")


def main() -> int:
    require_root()
    log(MIGRATION_ID, "PARTLABEL retrofit")

    root_source, disk = _root_disk()
    log(MIGRATION_ID, f"System disk: {disk} (from root {root_source})")

    root_resolved = Path(root_source).resolve()
    label_root = Path("/dev/disk/by-partlabel/homeserver-root")
    skip_sgdisk = False
    if label_root.exists():
        try:
            if label_root.resolve() == root_resolved:
                log(MIGRATION_ID, "PARTLABELs already applied (homeserver-root matches root)")
                skip_sgdisk = True
        except OSError:
            pass

    if not skip_sgdisk:
        _apply_partlabels(disk)
        subprocess.run(
            ["udevadm", "trigger", "--subsystem-match=block"],
            check=False,
        )
        time.sleep(1)

    missing = [lb for lb in LABELS if not Path(f"/dev/disk/by-partlabel/{lb}").exists()]
    if missing and not skip_sgdisk:
        log(MIGRATION_ID, f"WARNING: missing partlabel symlinks: {missing}", level="WARNING")
    elif not skip_sgdisk:
        log(MIGRATION_ID, "All PARTLABEL symlinks present")

    log(MIGRATION_ID, "SUCCESS: migration 00000007 complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
