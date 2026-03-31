#!/usr/bin/env python3
"""Migration 00000008: wan0/lan0 .link + .network + Kea drop-in + Kea interfaces JSON fix."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from migrations_common import log, require_root

MIGRATION_ID = "00000008"
NETWORK_DIR = Path("/etc/systemd/network")
WAN_LINK = NETWORK_DIR / "10-wan0.link"
LAN_LINK = NETWORK_DIR / "20-lan0.link"
WAN_NET = NETWORK_DIR / "10-wan0.network"
LAN_NET = NETWORK_DIR / "20-lan0.network"
DROPIN_DIR = Path("/etc/systemd/system/kea-dhcp4-server.service.d")
DROPIN_FILE = DROPIN_DIR / "override.conf"
KEA_CONF = Path("/etc/kea/kea-dhcp4.conf")

WAN_NET_BODY = """[Match]
Name=wan0

[Link]
ActivationPolicy=always-up

[Network]
DHCP=yes
IPForward=yes
DNSDefaultRoute=no
DNS=127.0.0.1
ConfigureWithoutCarrier=yes
IgnoreCarrierLoss=yes

[DHCP]
RouteMetric=10
UseDNS=no
UseDomains=no
UseNTP=no
"""

LAN_NET_BODY = """[Match]
Name=lan0

[Link]
ActivationPolicy=always-up

[Network]
Address=192.168.123.1/24
IPForward=yes
ConfigureWithoutCarrier=yes
IgnoreCarrierLoss=yes

[Route]
Metric=20
"""

DROPIN_BODY = """# Start Kea only after systemd-networkd has brought interfaces up.
[Unit]
After=systemd-networkd-wait-online.service
Wants=systemd-networkd-wait-online.service
"""


def _parse_ip_link_enp() -> list[str]:
    r = subprocess.run(["ip", "link", "show"], capture_output=True, text=True, check=False)
    out = []
    for line in (r.stdout or "").splitlines():
        m = re.match(r"^\s*(\d+):\s+([^:]+):", line)
        if not m:
            continue
        name = m.group(2)
        if not name.startswith("enp"):
            continue
        if name == "lo" or name.startswith("veth") or name.startswith("tailscale") or name.startswith("wlan"):
            continue
        out.append(name)
    return sorted(out)


def _write_link_file(path: Path, mac: str, stable: str) -> None:
    path.write_text(
        f"[Match]\nMACAddress={mac}\n\n[Link]\nName={stable}\n",
        encoding="utf-8",
    )
    path.chmod(0o644)


def _fix_kea_interfaces_json() -> None:
    """If Kea still references a kernel enp* name, set interfaces to lan0."""
    if not KEA_CONF.is_file():
        return
    try:
        data = json.loads(KEA_CONF.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        log(MIGRATION_ID, "WARNING: kea-dhcp4.conf not valid JSON; skipping interface fix", level="WARNING")
        return
    dhcp4 = data.get("Dhcp4")
    if not isinstance(dhcp4, dict):
        return
    icfg = dhcp4.get("interfaces-config")
    if not isinstance(icfg, dict):
        return
    ifaces = icfg.get("interfaces")
    if not isinstance(ifaces, list) or not ifaces:
        return
    changed = False
    new_ifaces = []
    for i in ifaces:
        if isinstance(i, str) and i.startswith("enp"):
            new_ifaces.append("lan0")
            changed = True
        else:
            new_ifaces.append(i)
    if changed:
        icfg["interfaces"] = new_ifaces
        dhcp4["interfaces-config"] = icfg
        data["Dhcp4"] = dhcp4
        KEA_CONF.write_text(json.dumps(data, indent=4) + "\n", encoding="utf-8")
        log(MIGRATION_ID, "Updated Kea interfaces-config to use lan0 (was enp*)")


def main() -> int:
    require_root()
    log(MIGRATION_ID, "Network .link/.network + Kea drop-in + Kea JSON")

    NETWORK_DIR.mkdir(parents=True, mode=0o755, exist_ok=True)

    if not WAN_LINK.is_file() or not LAN_LINK.is_file():
        interfaces = _parse_ip_link_enp()
        log(MIGRATION_ID, f"Discovered enp* interfaces: {interfaces}")
        if len(interfaces) < 1:
            log(MIGRATION_ID, "No eligible enp* interfaces", level="ERROR")
            return 1
        selected = interfaces[:2]
        for idx, if_name in enumerate(selected):
            addr_path = Path(f"/sys/class/net/{if_name}/address")
            if not addr_path.is_file():
                log(MIGRATION_ID, f"No MAC for {if_name}", level="ERROR")
                return 1
            mac = addr_path.read_text(encoding="utf-8").strip()
            if idx == 0:
                _write_link_file(WAN_LINK, mac, "wan0")
                log(MIGRATION_ID, f"Wrote {WAN_LINK} for {if_name} -> wan0")
            else:
                _write_link_file(LAN_LINK, mac, "lan0")
                log(MIGRATION_ID, f"Wrote {LAN_LINK} for {if_name} -> lan0")
        subprocess.run(["udevadm", "trigger"], check=False)
    else:
        log(MIGRATION_ID, "Both .link files exist; skipping link generation")

    WAN_NET.write_text(WAN_NET_BODY, encoding="utf-8")
    WAN_NET.chmod(0o644)
    LAN_NET.write_text(LAN_NET_BODY, encoding="utf-8")
    LAN_NET.chmod(0o644)
    log(MIGRATION_ID, f"Wrote {WAN_NET} and {LAN_NET}")

    subprocess.run(["networkctl", "reload"], check=False)
    subprocess.run(["networkctl", "reconfigure", "wan0"], check=False)
    subprocess.run(["networkctl", "reconfigure", "lan0"], check=False)

    need_dropin = True
    if DROPIN_FILE.is_file():
        try:
            if "systemd-networkd-wait-online" in DROPIN_FILE.read_text(encoding="utf-8"):
                log(MIGRATION_ID, "Kea drop-in already present, skipping")
                need_dropin = False
        except OSError:
            pass
    if need_dropin:
        DROPIN_DIR.mkdir(parents=True, mode=0o755, exist_ok=True)
        DROPIN_FILE.write_text(DROPIN_BODY, encoding="utf-8")
        DROPIN_FILE.chmod(0o644)
        subprocess.run(
            ["systemctl", "enable", "systemd-networkd-wait-online.service"],
            check=False,
        )
        subprocess.run(["systemctl", "daemon-reload"], check=False)
        log(MIGRATION_ID, "Installed Kea drop-in")

    _fix_kea_interfaces_json()

    log(MIGRATION_ID, "SUCCESS: migration 00000008 complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
