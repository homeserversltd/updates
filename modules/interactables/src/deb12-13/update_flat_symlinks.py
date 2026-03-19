#!/usr/bin/env python3
"""
Update flat symlinks for PostgreSQL and PHP-FPM after a distro upgrade.
Part of deb12-13 (Debian 12→13 in-place upgrade). Uses only stdlib.

PostgreSQL:
  /opt/homeserver/postgresql/current -> /etc/postgresql/VERSION/main
  /opt/homeserver/postgresql/bin -> /usr/lib/postgresql/VERSION/bin

PHP-FPM (baseline: Piwigo is the shipped PHP consumer; prefer the /etc/php/VERSION tree
that contains fpm/pool.d/piwigo.conf, else first version with pool.d):
  /opt/homeserver/php-fpm/current -> /etc/php/VERSION
  /opt/homeserver/php-fpm/bin/php-fpm -> php-fpmVERSION or phpVERSION-fpm (Debian)
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def log(msg: str, level: str = "INFO") -> None:
    print(f"update_flat_symlinks {level}: {msg}", file=sys.stderr if level != "INFO" else sys.stdout)


def run(cmd: list[str]) -> bool:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return r.returncode == 0


def main() -> int:
    if os.geteuid() != 0:
        log("Must run as root", "ERROR")
        return 1

    had_error = False

    # PostgreSQL
    pg_root = Path("/etc/postgresql")
    if pg_root.exists():
        versions = sorted([d.name for d in pg_root.iterdir() if d.is_dir()], reverse=True)
        if versions:
            pg_version = versions[0]
            main_dir = f"/etc/postgresql/{pg_version}/main"
            bin_dir = f"/usr/lib/postgresql/{pg_version}/bin"
            if Path(main_dir).exists() and Path(bin_dir).exists():
                flat = "/opt/homeserver/postgresql"
                if not run(["mkdir", "-p", flat]):
                    log(f"Failed to create {flat}", "ERROR")
                    had_error = True
                if not run(["ln", "-sfn", main_dir, f"{flat}/current"]):
                    log(f"Failed to link {flat}/current -> {main_dir}", "ERROR")
                    had_error = True
                if not run(["ln", "-sfn", bin_dir, f"{flat}/bin"]):
                    log(f"Failed to link {flat}/bin -> {bin_dir}", "ERROR")
                    had_error = True
                if Path(f"{flat}/current").exists() and Path(f"{flat}/bin/postgres").exists():
                    log(f"PostgreSQL flat symlinks updated -> {pg_version}")
                else:
                    log("PostgreSQL flat symlink validation failed", "ERROR")
                    had_error = True
            else:
                log(f"PostgreSQL dirs missing: {main_dir} or {bin_dir}", "WARNING")
                had_error = True
        else:
            log("No PostgreSQL version dir found", "WARNING")
            had_error = True
    else:
        log("/etc/postgresql not found (PostgreSQL not installed?)", "WARNING")
        had_error = True

    # PHP-FPM: prefer version dir that has Piwigo pool (product baseline); else any fpm/pool.d
    php_root = Path("/etc/php")
    if php_root.exists():
        php_version = None
        candidates: list[str] = []
        for d in sorted(php_root.iterdir(), reverse=True):
            if d.is_dir() and (d / "fpm/pool.d").exists():
                candidates.append(d.name)
        for dname in candidates:
            if (php_root / dname / "fpm/pool.d/piwigo.conf").is_file():
                php_version = dname
                break
        if php_version is None and candidates:
            php_version = candidates[0]
        if php_version:
            etc_php = f"/etc/php/{php_version}"
            # Debian: php-fpm{VERSION}; some distros use php{VERSION}-fpm
            php_fpm_bin = None
            for candidate in (f"/usr/sbin/php-fpm{php_version}", f"/usr/sbin/php{php_version}-fpm"):
                if Path(candidate).exists():
                    php_fpm_bin = candidate
                    break
            if php_fpm_bin:
                flat = "/opt/homeserver/php-fpm"
                if not run(["mkdir", "-p", f"{flat}/bin"]):
                    log(f"Failed to create {flat}/bin", "ERROR")
                    had_error = True
                if not run(["ln", "-sfn", etc_php, f"{flat}/current"]):
                    log(f"Failed to link {flat}/current -> {etc_php}", "ERROR")
                    had_error = True
                if not run(["ln", "-sfn", php_fpm_bin, f"{flat}/bin/php-fpm"]):
                    log(f"Failed to link {flat}/bin/php-fpm -> {php_fpm_bin}", "ERROR")
                    had_error = True
                if Path(f"{flat}/current/fpm/pool.d").exists() and Path(f"{flat}/bin/php-fpm").exists():
                    log(f"PHP-FPM flat symlinks updated -> {php_version}")
                else:
                    log("PHP-FPM flat symlink validation failed", "ERROR")
                    had_error = True
            else:
                log(f"PHP-FPM binary not found for {php_version} (tried php-fpm{php_version}, php{php_version}-fpm)", "WARNING")
                had_error = True
        else:
            log("No PHP FPM pool.d found", "WARNING")
            had_error = True
    else:
        log("/etc/php not found (PHP not installed?)", "WARNING")
        had_error = True

    return 1 if had_error else 0


if __name__ == "__main__":
    sys.exit(main())
