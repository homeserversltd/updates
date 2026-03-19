#!/usr/bin/python3
"""
Interactable: PostgreSQL 15 → 17 in-place upgrade (pg_upgrade).
WARNING: May break your shit. Backup databases and /etc/postgresql/15 before running.
Stops dependent services (Vaultwarden, Gogs/Forgejo, FreshRSS), runs pg_upgrade,
updates our postgresql.service and any units that reference postgresql@15-main
(e.g. vaultwarden.service) to postgresql@17-main, then starts services.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

LOG_FILE = os.environ.get("LOG_FILE", "/var/log/homeserver/migrations.log")
ID = "postgres15_to_17"
OLD_VER = "15"
NEW_VER = "17"
OLD_DATADIR = f"/etc/postgresql/{OLD_VER}/main"
NEW_DATADIR = f"/etc/postgresql/{NEW_VER}/main"
OLD_BIN = f"/usr/lib/postgresql/{OLD_VER}/bin"
NEW_BIN = f"/usr/lib/postgresql/{NEW_VER}/bin"
SYSTEMD_SYSTEM = Path("/etc/systemd/system")
DEPENDENT_SVCS = ["vaultwarden", "gogs", "forgejo", "freshrss"]


def _log(msg: str, level: str = "INFO") -> None:
    line = f"{ID}: {msg}\n"
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line)
    except OSError:
        pass
    prefix = f"{ID} {level}: " if level != "INFO" else f"{ID}: "
    (sys.stderr if level != "INFO" else sys.stdout).write(prefix + msg + "\n")


def _run(cmd: list[str], check: bool = True, capture: bool = False, timeout: int = 300) -> subprocess.CompletedProcess:
    env = {**os.environ, "DEBIAN_FRONTEND": "noninteractive"}
    r = subprocess.run(
        cmd,
        capture_output=capture,
        text=True,
        timeout=timeout,
        env=env,
    )
    if check and r.returncode != 0:
        raise RuntimeError(f"Command failed: {cmd!r} -> {r.stderr or r.stdout or r.returncode}")
    return r


def main() -> int:
    # Banner
    print("")
    print("==============================================")
    print("  POSTGRESQL 15 → 17 MIGRATION (pg_upgrade)")
    print("==============================================")
    print("")
    print("  *** THIS MAY BREAK YOUR SHIT ***")
    print("")
    print("  - Services that use PostgreSQL (Vaultwarden, Gogs/Forgejo, FreshRSS)")
    print("    will be stopped during the migration.")
    print("  - If anything fails, you may need manual intervention (recovery from")
    print("    backup, or fixing the cluster by hand).")
    print("  - Backup your databases and /etc/postgresql/15 before running.")
    print("  - This is entirely at your own risk.")
    print("")
    print("==============================================")
    print("")

    if os.geteuid() != 0:
        _log("Must run as root", "ERROR")
        return 1

    try:
        # Preflight: PostgreSQL 15 must exist
        if not Path(OLD_DATADIR).is_dir() or not (Path(OLD_DATADIR) / "PG_VERSION").exists():
            _log(f"PostgreSQL {OLD_VER} cluster not found at {OLD_DATADIR}. Nothing to migrate.", "ERROR")
            return 1
        if not Path(f"{OLD_BIN}/pg_ctl").is_file() or not os.access(f"{OLD_BIN}/pg_ctl", os.X_OK):
            _log(f"PostgreSQL {OLD_VER} binaries not found at {OLD_BIN}. Install postgresql-{OLD_VER}.", "ERROR")
            return 1

        # PostgreSQL 17 must be available (install if missing)
        if not Path(f"{NEW_BIN}/initdb").is_file() or not os.access(f"{NEW_BIN}/initdb", os.X_OK):
            _log(f"PostgreSQL {NEW_VER} not installed; installing postgresql-{NEW_VER}...")
            _run(["/usr/bin/apt-get", "update", "-qq"], timeout=60)
            _run(["/usr/bin/apt-get", "install", "-y", "-qq", f"postgresql-{NEW_VER}"], timeout=120)
        if not Path(f"{NEW_BIN}/pg_upgrade").is_file() or not os.access(f"{NEW_BIN}/pg_upgrade", os.X_OK):
            _log(f"pg_upgrade not found at {NEW_BIN}/pg_upgrade.", "ERROR")
            return 1

        # Refuse if new cluster already exists
        if Path(NEW_DATADIR).is_dir() and (Path(NEW_DATADIR) / "PG_VERSION").exists():
            _log(f"PostgreSQL {NEW_VER} cluster already exists at {NEW_DATADIR}. Remove it first if you intend to re-run.", "ERROR")
            return 1

        _log("Stopping services that depend on PostgreSQL...")
        for svc in DEPENDENT_SVCS:
            subprocess.run(["/bin/systemctl", "stop", svc], capture_output=True, timeout=10)
        _log("Stopping PostgreSQL...")
        subprocess.run(["/bin/systemctl", "stop", "postgresql"], capture_output=True, timeout=10)
        _run(["/bin/sleep", "2"])

        # Ensure old cluster is really down
        r = subprocess.run(["pgrep", "-f", f"postgres -D {OLD_DATADIR}"], capture_output=True, timeout=5)
        if r.returncode == 0 and r.stdout.strip():
            _log("Old PostgreSQL cluster still running; aborting.", "ERROR")
            return 1

        _log("Creating new cluster directory and initializing...")
        Path(NEW_DATADIR).mkdir(parents=True, exist_ok=True)
        _run(["/bin/chown", "postgres:postgres", NEW_DATADIR])
        _run(["/bin/chmod", "700", NEW_DATADIR])
        _run(["/usr/bin/sudo", "-u", "postgres", f"{NEW_BIN}/initdb", "-D", NEW_DATADIR, "-E", "UTF8", "--locale=en_US.UTF-8"], timeout=30)

        _log("Running pg_upgrade --check (dry run)...")
        _run([
            "/usr/bin/sudo", "-u", "postgres", f"{NEW_BIN}/pg_upgrade",
            "-b", OLD_BIN, "-B", NEW_BIN,
            "-d", OLD_DATADIR, "-D", NEW_DATADIR,
            "--check", "-U", "postgres",
        ], timeout=120)

        _log("Running pg_upgrade (actual migration)...")
        _run([
            "/usr/bin/sudo", "-u", "postgres", f"{NEW_BIN}/pg_upgrade",
            "-b", OLD_BIN, "-B", NEW_BIN,
            "-d", OLD_DATADIR, "-D", NEW_DATADIR,
            "-U", "postgres", "-k",
        ], timeout=600)

        # Copy config from old cluster and fix paths
        _log("Copying and adjusting configuration...")
        _run(["/bin/cp", "-a", f"{OLD_DATADIR}/pg_hba.conf", f"{NEW_DATADIR}/"])
        _run(["/bin/cp", "-a", f"{OLD_DATADIR}/postgresql.conf", f"{NEW_DATADIR}/"])
        with open(f"{NEW_DATADIR}/postgresql.conf", "r") as f:
            content = f.read()
        with open(f"{NEW_DATADIR}/postgresql.conf", "w") as f:
            f.write(content.replace(f"/{OLD_VER}/", f"/{NEW_VER}/"))
        old_conf_d = Path(OLD_DATADIR) / "conf.d"
        if old_conf_d.is_dir():
            _run(["/bin/cp", "-a", str(old_conf_d), f"{NEW_DATADIR}/"])
            _run(["/bin/chown", "-R", "postgres:postgres", f"{NEW_DATADIR}/conf.d"])

        # Update our postgresql.service
        pg_unit = SYSTEMD_SYSTEM / "postgresql.service"
        if pg_unit.exists():
            _log(f"Updating systemd unit to PostgreSQL {NEW_VER}...")
            text = pg_unit.read_text()
            pg_unit.write_text(text.replace(OLD_VER, NEW_VER))

        # Update any unit that references postgresql@OLD_VER-main (e.g. vaultwarden.service)
        # Handles both already-substituted (postgresql@15-main) and placeholder (postgresql@${PG_VERSION}-main)
        replacement = f"postgresql@{NEW_VER}-main"
        updated_units = []
        for unit in SYSTEMD_SYSTEM.glob("*.service"):
            try:
                text = unit.read_text()
                changed = False
                if f"postgresql@{OLD_VER}-main" in text:
                    text = text.replace(f"postgresql@{OLD_VER}-main", replacement)
                    changed = True
                if "postgresql@${PG_VERSION}-main" in text:
                    text = text.replace("postgresql@${PG_VERSION}-main", replacement)
                    changed = True
                if changed:
                    unit.write_text(text)
                    updated_units.append(unit.name)
            except (OSError, IOError):
                pass
        if updated_units:
            _log(f"Updated units to postgresql@{NEW_VER}-main: {', '.join(updated_units)}")

        _run(["/bin/systemctl", "daemon-reload"], timeout=10)

        _log(f"Starting PostgreSQL {NEW_VER}...")
        _run(["/bin/systemctl", "start", "postgresql"], timeout=30)

        _log("Running ANALYZE on all databases...")
        subprocess.run(["/usr/bin/sudo", "-u", "postgres", f"{NEW_BIN}/vacuumdb", "-a", "-z"], capture_output=True, timeout=300)

        _log("Starting dependent services...")
        for svc in DEPENDENT_SVCS:
            subprocess.run(["/bin/systemctl", "start", svc], capture_output=True, timeout=15)

        _log("PostgreSQL 15 → 17 migration complete.")
        _log(f"Old cluster left at {OLD_DATADIR}. After verifying apps, remove with: rm -rf {OLD_DATADIR}")
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
