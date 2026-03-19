#!/usr/bin/python3
"""
Interactable: Migrate PHP-FPM pool configs and systemd units to the default PHP version.
After a distro upgrade (e.g. Debian 12→13) the default PHP may be newer; pool configs
and units can still point at the old version. This script detects current (in-use) and
default (new) PHP versions at runtime and migrates without hardcoding version numbers.
Also installs the RuntimeDirectory drop-in for the distro php-X-fpm unit so /run/php
exists at boot (avoids "unable to bind listening socket" after reboot).
WARNING: Can fuck your shit up. Backup and run at your own risk. Only shown after Debian 12→13.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

LOG_FILE = os.environ.get("LOG_FILE", "/var/log/homeserver/migrations.log")
ID = "php_fpm_migrate"
KNOWN_POOLS = ["piwigo", "ampache", "freshrss"]
SYSTEMD_SYSTEM = Path("/etc/systemd/system")
PHP_FPM_RUNTIME_OVERRIDE = """# Ensure /run/php exists so the distro PHP-FPM www pool can create its socket there.
# Without this, php8.x-fpm fails with: unable to bind listening socket for address
# '/run/php/php8.x-fpm.sock': No such file or directory (distro unit has no RuntimeDirectory).
[Service]
RuntimeDirectory=php
RuntimeDirectoryMode=0755
"""


def _log(msg: str, level: str = "INFO") -> None:
    line = f"{ID}: {msg}\n"
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line)
    except OSError:
        pass
    prefix = f"{ID} {level}: " if level != "INFO" else f"{ID}: "
    (sys.stderr if level != "INFO" else sys.stdout).write(prefix + msg + "\n")


def _run(cmd: list[str], check: bool = True, capture: bool = False, timeout: int = 120) -> subprocess.CompletedProcess:
    env = {**os.environ, "DEBIAN_FRONTEND": "noninteractive"}
    r = subprocess.run(cmd, capture_output=capture, text=True, timeout=timeout, env=env)
    if check and r.returncode != 0:
        raise RuntimeError(f"Command failed: {cmd!r} -> {r.stderr or r.stdout or r.returncode}")
    return r


def _detect_new_php_version() -> str:
    r = subprocess.run(
        ["/usr/bin/php", "-r", "echo PHP_MAJOR_VERSION.'.'.PHP_MINOR_VERSION;"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    if r.returncode != 0 or not r.stdout or not r.stdout.strip():
        raise RuntimeError("Could not detect default PHP version (php -r ... failed).")
    return r.stdout.strip()


def _detect_old_php_version() -> str | None:
    etc_php = Path("/etc/php")
    if not etc_php.is_dir():
        return None
    for d in sorted(etc_php.iterdir()):
        if not d.is_dir():
            continue
        pool_d = d / "fpm" / "pool.d"
        if not pool_d.is_dir():
            continue
        for name in KNOWN_POOLS:
            if (pool_d / f"{name}.conf").is_file():
                return d.name
    return None


def main() -> int:
    print("")
    print("==============================================")
    print("  PHP-FPM MIGRATION TO DEFAULT PHP")
    print("==============================================")
    print("")
    print("  *** THIS CAN FUCK YOUR SHIT UP ***")
    print("")
    print("  - PHP-FPM services (Piwigo, Ampache, FreshRSS) will be restarted.")
    print("  - Pool configs will be copied to the new PHP version; systemd units updated.")
    print("  - RuntimeDirectory drop-in will be installed so /run/php exists at boot.")
    print("  - Old PHP version remains installed until you remove it (after verifying).")
    print("")
    print("==============================================")
    print("")

    if os.geteuid() != 0:
        _log("Must run as root", "ERROR")
        return 1

    try:
        new_ver = _detect_new_php_version()
        old_ver = _detect_old_php_version()

        if not old_ver:
            _log(
                f"No known PHP-FPM pool configs ({', '.join(KNOWN_POOLS)}) found under any /etc/php/*/fpm/pool.d. Nothing to migrate.",
                "ERROR",
            )
            return 1

        if old_ver == new_ver:
            _log(
                f"Default PHP is already {new_ver}; pool configs are already under that version. Nothing to migrate.",
                "ERROR",
            )
            return 1

        pool_src = Path(f"/etc/php/{old_ver}/fpm/pool.d")
        pool_dst = Path(f"/etc/php/{new_ver}/fpm/pool.d")

        _log(f"PHP-FPM migration: {old_ver} → {new_ver}")

        # Ensure new PHP FPM is installed
        php_fpm_bin = f"/usr/sbin/php-fpm{new_ver}"
        if not Path(php_fpm_bin).exists():
            php_fpm_bin = f"/usr/sbin/php{new_ver}-fpm"
        if not Path(php_fpm_bin).exists():
            _log(f"PHP {new_ver} FPM not installed; installing php{new_ver}-fpm...")
            _run(["/usr/bin/apt-get", "update", "-qq"], timeout=60)
            _run(["/usr/bin/apt-get", "install", "-y", "-qq", f"php{new_ver}-fpm"], timeout=120)
        if not pool_dst.is_dir():
            _log(f"PHP {new_ver} pool.d not found at {pool_dst} after install.", "ERROR")
            return 1

        # Copy known pool configs from old to new
        copied = 0
        for name in KNOWN_POOLS:
            src_file = pool_src / f"{name}.conf"
            if src_file.is_file():
                shutil.copy2(src_file, pool_dst / f"{name}.conf")
                _log(f"Copied pool {name}.conf to PHP {new_ver}")
                copied += 1
        if copied == 0:
            _log(f"No known pool configs found in {pool_src}; nothing copied.", "WARNING")

        # Update piwigo.service if it references old PHP version
        piwigo_unit = SYSTEMD_SYSTEM / "piwigo.service"
        if piwigo_unit.is_file():
            text = piwigo_unit.read_text()
            if old_ver in text or f"php-fpm{old_ver}" in text:
                text = text.replace(old_ver, new_ver).replace(f"php-fpm{old_ver}", f"php-fpm{new_ver}")
                piwigo_unit.write_text(text)
                _log(f"Updated {piwigo_unit} to PHP {new_ver}")

        # Install RuntimeDirectory drop-in for php{NEW_VER}-fpm so /run/php exists at boot
        dropin_dir = SYSTEMD_SYSTEM / f"php{new_ver}-fpm.service.d"
        dropin_dir.mkdir(parents=True, exist_ok=True)
        override_path = dropin_dir / "override.conf"
        override_path.write_text(PHP_FPM_RUNTIME_OVERRIDE)
        _log(f"Installed php{new_ver}-fpm RuntimeDirectory drop-in at {override_path}")

        _run(["/bin/systemctl", "daemon-reload"], timeout=10)

        # Restart new PHP FPM and Piwigo (standalone pool) if enabled
        _log(f"Restarting php{new_ver}-fpm...")
        _run(["/bin/systemctl", "restart", f"php{new_ver}-fpm"], timeout=30)
        r = subprocess.run(
            ["/bin/systemctl", "is-enabled", "piwigo.service"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode == 0 and "enabled" in (r.stdout or "").lower():
            _log("Restarting piwigo.service...")
            subprocess.run(["/bin/systemctl", "restart", "piwigo.service"], capture_output=True, timeout=15)

        _log(f"PHP-FPM migration complete ({old_ver} → {new_ver}).")
        _log(f"Old PHP {old_ver} configs remain at {pool_src}. After verifying, you can remove php{old_ver}-fpm if desired.")
        print("")
        return 0

    except subprocess.TimeoutExpired as e:
        _log(f"Command timed out: {e.cmd}", "ERROR")
        return 1
    except Exception as e:
        _log(str(e), "ERROR")
        return 1


if __name__ == "__main__":
    sys.exit(main())
