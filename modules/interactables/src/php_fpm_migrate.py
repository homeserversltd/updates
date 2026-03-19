#!/usr/bin/python3
"""
Interactable: Migrate Piwigo PHP-FPM pool to the default PHP version after distro upgrade.
Copies pool.d/piwigo.conf, installs HOMESERVER php-fpm.service (flat paths), disables distro
phpX.Y-fpm units, enables php-fpm. Keep in sync with
homeserver/initialization/networkservices/piwigo/config/php-fpm.service.
WARNING: Can fuck your shit up. Backup first. Only shown after Debian 12→13.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

LOG_FILE = os.environ.get("LOG_FILE", "/var/log/homeserver/migrations.log")
ID = "php_fpm_migrate"
# Baseline product PHP surface is Piwigo only (single pool to migrate)
KNOWN_POOLS = ["piwigo"]
SYSTEMD_SYSTEM = Path("/etc/systemd/system")

# Must match networkservices/piwigo/config/php-fpm.service (single source of truth in repo)
HOMESERVER_PHP_FPM_UNIT = """# HOMESERVER-managed PHP-FPM: paths via /opt/homeserver/php-fpm/current (symlink).
# Portal config: services ["php-fpm"] — no PHP version numbers in homeserver.json.
# Installer disables the distro phpX.Y-fpm unit so only this master runs (all pools in pool.d).
[Unit]
Description=HOMESERVER PHP-FPM (flat /opt/homeserver/php-fpm/current)
Documentation=man:php-fpm8.4(8)
After=network.target

[Service]
Type=notify
RuntimeDirectory=php
RuntimeDirectoryMode=0755
ExecStart=/opt/homeserver/php-fpm/bin/php-fpm --nodaemonize --fpm-config /opt/homeserver/php-fpm/current/fpm/php-fpm.conf
ExecStartPost=-/usr/lib/php/php-fpm-socket-helper install /run/php/php-fpm.sock /opt/homeserver/php-fpm/current/fpm/pool.d/www.conf 84
ExecStopPost=-/usr/lib/php/php-fpm-socket-helper remove /run/php/php-fpm.sock /opt/homeserver/php-fpm/current/fpm/pool.d/www.conf 84
ExecReload=/bin/kill -USR2 $MAINPID
Restart=on-failure

[Install]
WantedBy=multi-user.target
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
    print("  - Pool configs copied to new PHP version; flat symlinks should point at new paths.")
    print("  - HOMESERVER php-fpm.service installed; distro phpX.Y-fpm disabled.")
    print("  - Old PHP packages may remain until you remove them after verifying.")
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

        copied = 0
        for name in KNOWN_POOLS:
            src_file = pool_src / f"{name}.conf"
            if src_file.is_file():
                shutil.copy2(src_file, pool_dst / f"{name}.conf")
                _log(f"Copied pool {name}.conf to PHP {new_ver}")
                copied += 1
        if copied == 0:
            _log(f"No known pool configs found in {pool_src}; nothing copied.", "WARNING")

        # Flat symlinks: /opt/homeserver/php-fpm/current → /etc/php/{new_ver}
        flat_root = Path("/opt/homeserver/php-fpm")
        etc_new = Path(f"/etc/php/{new_ver}")
        if flat_root.is_dir() and etc_new.is_dir():
            (flat_root / "bin").mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["/bin/ln", "-sfn", str(etc_new), str(flat_root / "current")],
                check=False,
                timeout=5,
            )
            for candidate in (f"/usr/sbin/php-fpm{new_ver}", f"/usr/sbin/php{new_ver}-fpm"):
                if Path(candidate).exists():
                    subprocess.run(
                        ["/bin/ln", "-sfn", candidate, str(flat_root / "bin" / "php-fpm")],
                        check=False,
                        timeout=5,
                    )
                    break
            _log(f"Updated flat symlinks under {flat_root} to PHP {new_ver}")

        # HOMESERVER php-fpm.service
        unit_path = SYSTEMD_SYSTEM / "php-fpm.service"
        unit_path.write_text(HOMESERVER_PHP_FPM_UNIT)
        _log(f"Wrote {unit_path}")

        piwigo_unit = SYSTEMD_SYSTEM / "piwigo.service"
        if piwigo_unit.is_file():
            text = piwigo_unit.read_text()
            if old_ver in text or f"php-fpm{old_ver}" in text:
                text = text.replace(old_ver, new_ver).replace(f"php-fpm{old_ver}", f"php-fpm{new_ver}")
                piwigo_unit.write_text(text)
                _log(f"Updated {piwigo_unit} path references if any")

        _run(["/bin/systemctl", "daemon-reload"], timeout=10)
        subprocess.run(["/bin/systemctl", "disable", "--now", f"php{old_ver}-fpm"], capture_output=True, timeout=15)
        subprocess.run(["/bin/systemctl", "disable", "--now", f"php{new_ver}-fpm"], capture_output=True, timeout=15)
        _run(["/bin/systemctl", "enable", "php-fpm"], timeout=10)
        _run(["/bin/systemctl", "restart", "php-fpm"], timeout=30)

        r = subprocess.run(
            ["/bin/systemctl", "is-enabled", "piwigo.service"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode == 0 and "enabled" in (r.stdout or "").lower():
            _log("Restarting piwigo.service (optional standalone unit)...")
            subprocess.run(["/bin/systemctl", "restart", "piwigo.service"], capture_output=True, timeout=15)

        _log(f"PHP-FPM migration complete ({old_ver} → {new_ver}); HOMESERVER php-fpm.service is active.")
        _log(f"Old configs remain at {pool_src}. Remove php{old_ver}-fpm when satisfied.")
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
