#!/usr/bin/env python3
"""
Update flat symlinks for PostgreSQL and PHP-FPM after a distro upgrade.
Part of deb12-13 (Debian 12→13 in-place upgrade). Uses only stdlib.
Creates/updates:
  /opt/homeserver/postgresql/current -> /etc/postgresql/VERSION/main
  /opt/homeserver/postgresql/bin -> /usr/lib/postgresql/VERSION/bin
  /opt/homeserver/php-fpm/current -> /etc/php/VERSION
  /opt/homeserver/php-fpm/bin/php-fpm -> /usr/sbin/phpVERSION-fpm
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

    # PostgreSQL
    pg_root = Path("/etc/postgresql")
    if pg_root.exists():
        versions = [d.name for d in pg_root.iterdir() if d.is_dir()]
        if versions:
            pg_version = versions[0]
            main_dir = f"/etc/postgresql/{pg_version}/main"
            bin_dir = f"/usr/lib/postgresql/{pg_version}/bin"
            if Path(main_dir).exists() and Path(bin_dir).exists():
                flat = "/opt/homeserver/postgresql"
                run(["mkdir", "-p", flat])
                run(["ln", "-sfn", main_dir, f"{flat}/current"])
                run(["ln", "-sfn", bin_dir, f"{flat}/bin"])
                log(f"PostgreSQL flat symlinks updated -> {pg_version}")
            else:
                log(f"PostgreSQL dirs missing: {main_dir} or {bin_dir}", "WARNING")
        else:
            log("No PostgreSQL version dir found", "WARNING")
    else:
        log("/etc/postgresql not found (PostgreSQL not installed?)", "WARNING")

    # PHP-FPM
    php_root = Path("/etc/php")
    if php_root.exists():
        php_version = None
        for d in sorted(php_root.iterdir()):
            if d.is_dir() and (d / "fpm/pool.d").exists():
                php_version = d.name
                break
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
                run(["mkdir", "-p", f"{flat}/bin"])
                run(["ln", "-sfn", etc_php, f"{flat}/current"])
                run(["ln", "-sfn", php_fpm_bin, f"{flat}/bin/php-fpm"])
                log(f"PHP-FPM flat symlinks updated -> {php_version}")
            else:
                log(f"PHP-FPM binary not found for {php_version} (tried php-fpm{php_version}, php{php_version}-fpm)", "WARNING")
        else:
            log("No PHP FPM pool.d found", "WARNING")
    else:
        log("/etc/php not found (PHP not installed?)", "WARNING")

    return 0


if __name__ == "__main__":
    sys.exit(main())
