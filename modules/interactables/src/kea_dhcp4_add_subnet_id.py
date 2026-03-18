#!/usr/bin/python3
"""
Patch /etc/kea/kea-dhcp4.conf: add explicit subnet "id" to each subnet that lacks one.
Required by Kea 2.6+ (Debian 13 Trixie); harmless on Kea 2.2 (Debian 12 Bookworm).
Exit: 0 = config patched, 1 = error, 2 = no change needed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    config_path = Path(sys.argv[1] if len(sys.argv) > 1 else "/etc/kea/kea-dhcp4.conf")

    try:
        with open(config_path) as f:
            cfg = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"kea_dhcp4_add_subnet_id: failed to read {config_path}: {e}", file=sys.stderr)
        return 1

    dhcp4 = cfg.get("Dhcp4") or {}
    subnets = dhcp4.get("subnet4") or []
    if not isinstance(subnets, list):
        print(f"kea_dhcp4_add_subnet_id: Dhcp4.subnet4 is not a list in {config_path}", file=sys.stderr)
        return 1

    changed = False
    for i, sn in enumerate(subnets):
        if isinstance(sn, dict) and "id" not in sn:
            sn["id"] = i + 1
            changed = True

    if not changed:
        return 2

    try:
        with open(config_path, "w") as f:
            json.dump(cfg, f, indent=4)
    except OSError as e:
        print(f"kea_dhcp4_add_subnet_id: failed to write {config_path}: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
