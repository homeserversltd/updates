#!/usr/bin/python3
"""
Orchestrator for Debian 12 → 13 in-place upgrade.
Loads config from index.json, resolves paths, runs steps sequentially.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _load_config(module_path: Path) -> dict:
    with open(module_path / "index.json") as f:
        return json.load(f)


def _resolve_paths(paths_config: dict) -> dict:
    return {k: os.path.expandvars(str(v)) for k, v in paths_config.items()}


def _log(log_file: Path, msg: str, level: str = "INFO") -> None:
    line = f"debian12_to_13: {msg}\n"
    try:
        with open(log_file, "a") as f:
            f.write(line)
    except OSError:
        pass
    prefix = f"debian12_to_13 {level}: " if level != "INFO" else "debian12_to_13: "
    print(prefix + msg, file=sys.stderr if level != "INFO" else sys.stdout)


def _run(cmd: list[str], timeout: int = 300) -> tuple[bool, str, str]:
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "DEBIAN_FRONTEND": "noninteractive"},
        )
        return r.returncode == 0, r.stdout or "", r.stderr or ""
    except subprocess.TimeoutExpired:
        return False, "", "Command timed out"
    except Exception as e:
        return False, "", str(e)


def main(module_path: Path | None = None) -> int:
    module_path = module_path or Path(__file__).resolve().parent
    config = _load_config(module_path)
    paths = _resolve_paths(config.get("paths", {}))
    cfg = config.get("config", {})
    log_file = Path(paths["log_file"])
    backup_dir = Path(paths["backup_dir"])
    sources_list = Path(paths["sources_list"])
    sources_d = Path(paths["sources_d"])
    kea_conf = Path(paths["kea_conf"])
    kea_patch = module_path / paths["kea_patch_script"]
    id_tag = cfg.get("id", "debian12_to_13")

    if os.geteuid() != 0:
        _log(log_file, "Must run as root", "ERROR")
        return 1

    try:
        current = subprocess.run(
            ["/usr/bin/lsb_release", "-cs"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        codename = (current.stdout or "").strip() if current.returncode == 0 else ""
    except Exception:
        codename = ""
    if codename != "bookworm":
        _log(log_file, f"This migration is for Debian 12 (bookworm) only. Current: {codename or 'unknown'}", "ERROR")
        return 1

    _log(log_file, "Starting Debian 12 → 13 in-place upgrade")

    # 1) Backup APT sources
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = subprocess.run(["date", "+%Y%m%d%H%M%S"], capture_output=True, text=True, timeout=2)
    ts = (timestamp.stdout or "00000000000000").strip()
    if sources_list.exists():
        dest = backup_dir / f"sources.list.{ts}"
        try:
            with open(sources_list) as f:
                content = f.read()
            with open(dest, "w") as f:
                f.write(content)
        except OSError as e:
            _log(log_file, f"Backup sources.list failed: {e}", "WARNING")
    for pattern in ["*.list", "*.sources"]:
        for f in sources_d.glob(pattern):
            try:
                dest = backup_dir / f"{f.name}.{ts}"
                with open(f) as src:
                    with open(dest, "w") as out:
                        out.write(src.read())
            except OSError:
                pass
    _log(log_file, f"Backed up APT sources to {backup_dir}")

    # 2) Remove bookworm-backports
    for pattern in ["bookworm-backports*.list", "bookworm-backports*.sources"]:
        for f in sources_d.glob(pattern):
            try:
                f.unlink()
                _log(log_file, f"Removed {f}")
            except OSError:
                pass

    # 3) Replace bookworm with trixie in main list
    if sources_list.exists():
        try:
            text = sources_list.read_text()
            sources_list.write_text(text.replace("bookworm", "trixie"))
            _log(log_file, f"Updated {sources_list} bookworm → trixie")
        except OSError as e:
            _log(log_file, f"Update sources.list failed: {e}", "WARNING")

    # 4) Replace in sources.d
    for g in [sources_d.glob("*.list"), sources_d.glob("*.sources")]:
        for f in g:
            try:
                text = f.read_text()
                if "bookworm" in text:
                    f.write_text(text.replace("bookworm", "trixie"))
                    _log(log_file, f"Updated {f} bookworm → trixie")
            except OSError:
                pass

    # 5) Kea DHCP4 subnet id patch
    if kea_conf.exists() and kea_patch.is_file():
        try:
            r = subprocess.run(
                ["/usr/bin/python3", str(kea_patch), str(kea_conf)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            rc = r.returncode
        except (subprocess.TimeoutExpired, OSError):
            rc = -1
        if rc == 0:
            _log(log_file, f"Patched {kea_conf}: added subnet id(s) for Kea 2.6 compatibility")
        elif rc == 2:
            _log(log_file, f"Kea config {kea_conf} already has subnet id(s), no change")
        else:
            _log(log_file, f"Could not parse or patch {kea_conf} (non-fatal); Kea may fail after upgrade until config has subnet id", "WARNING")
    elif kea_conf.exists():
        _log(log_file, f"Kea patch script {kea_patch} missing (non-fatal)", "WARNING")

    # 6) apt update and full-upgrade
    _log(log_file, "Running apt update")
    ok, out, err = _run(["/usr/bin/apt-get", "update", "-y"], timeout=120)
    if not ok:
        _log(log_file, f"apt update failed: {err}", "ERROR")
        return 1
    _log(log_file, "Running apt full-upgrade (may take several minutes)")
    ok, out, err = _run(["/usr/bin/apt-get", "full-upgrade", "-y"], timeout=1800)
    if not ok:
        _log(log_file, f"apt full-upgrade failed: {err}", "ERROR")
        return 1

    # 7) Add trixie-backports
    backports_file = sources_d / cfg.get("backports_filename", "trixie-backports.list")
    backports_file.write_text(cfg.get("backports_line", "deb http://deb.debian.org/debian trixie-backports main") + "\n")
    _log(log_file, "Added trixie-backports")
    _run(["/usr/bin/apt-get", "update", "-y"], timeout=120)

    # 8) Cleanup
    _run(["/usr/bin/apt-get", "autoremove", "-y"], timeout=300)
    _run(["/usr/bin/apt-get", "autoclean"], timeout=60)

    _log(log_file, "Debian 12 → 13 upgrade step completed. REBOOT REQUIRED (new kernel).")
    print("")
    print(f"{id_tag}: REBOOT REQUIRED. Run: sudo reboot")
    print("")
    print("After reboot, if you use PostgreSQL or PHP-FPM (Piwigo, Ampache, FreshRSS),")
    print("run the 'PostgreSQL 15→17' and 'PHP-FPM migration to default PHP' interactables from Admin → Updates.")
    print("Those migrations can fuck your shit up; run them when ready.")
    print("")
    return 0


if __name__ == "__main__":
    sys.exit(main())
