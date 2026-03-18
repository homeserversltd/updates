#!/bin/bash
# Interactable: PostgreSQL 15 → 17 in-place upgrade (pg_upgrade).
# WARNING: May break your shit. Requires manual intervention if something goes wrong.
# Backup your databases and /etc/postgresql/15 before running. Proceed at your own risk.
set -e

LOG_FILE="${LOG_FILE:-/var/log/homeserver/migrations.log}"
ID="postgres15_to_17"
OLD_VER="15"
NEW_VER="17"
OLD_DATADIR="/etc/postgresql/${OLD_VER}/main"
NEW_DATADIR="/etc/postgresql/${NEW_VER}/main"
OLD_BIN="/usr/lib/postgresql/${OLD_VER}/bin"
NEW_BIN="/usr/lib/postgresql/${NEW_VER}/bin"

INFO()  { echo "$ID: $*" | tee -a "$LOG_FILE"; }
WARN()  { echo "$ID WARNING: $*" | tee -a "$LOG_FILE" >&2; }
ERROR() { echo "$ID ERROR: $*" | tee -a "$LOG_FILE" >&2; exit 1; }

# ---------- WARNINGS (displayed in UI / log) ----------
echo ""
echo "=============================================="
echo "  POSTGRESQL 15 → 17 MIGRATION (pg_upgrade)"
echo "=============================================="
echo ""
echo "  *** THIS MAY BREAK YOUR SHIT ***"
echo ""
echo "  - Services that use PostgreSQL (Vaultwarden, Gogs/Forgejo, FreshRSS)"
echo "    will be stopped during the migration."

echo "  - If anything fails, you may need manual intervention (recovery from"
echo "    backup, or fixing the cluster by hand)."
echo ""
echo "  - Backup your databases and /etc/postgresql/15 before running."
echo "  - This is entirely at your own risk."
echo ""
echo "=============================================="
echo ""

if [ "$EUID" -ne 0 ]; then
    ERROR "Must run as root"
fi

# Preflight: PostgreSQL 15 must exist
if [ ! -d "$OLD_DATADIR" ] || [ ! -f "$OLD_DATADIR/PG_VERSION" ]; then
    ERROR "PostgreSQL ${OLD_VER} cluster not found at $OLD_DATADIR. Nothing to migrate."
fi
if [ ! -x "$OLD_BIN/pg_ctl" ]; then
    ERROR "PostgreSQL ${OLD_VER} binaries not found at $OLD_BIN. Install postgresql-${OLD_VER}."
fi

# PostgreSQL 17 must be available (install if missing)
if [ ! -x "$NEW_BIN/initdb" ]; then
    INFO "PostgreSQL ${NEW_VER} not installed; installing postgresql-${NEW_VER}..."
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq && apt-get install -y -qq postgresql-${NEW_VER} || ERROR "Failed to install postgresql-${NEW_VER}"
fi
if [ ! -x "$NEW_BIN/pg_upgrade" ]; then
    ERROR "pg_upgrade not found at $NEW_BIN/pg_upgrade."
fi

# Refuse if new cluster already exists (safety)
if [ -d "$NEW_DATADIR" ] && [ -f "$NEW_DATADIR/PG_VERSION" ]; then
    ERROR "PostgreSQL ${NEW_VER} cluster already exists at $NEW_DATADIR. Remove it first if you intend to re-run, or abort."
fi

INFO "Stopping services that depend on PostgreSQL..."
for svc in vaultwarden gogs forgejo freshrss; do
    systemctl stop "$svc" 2>/dev/null || true
done
INFO "Stopping PostgreSQL..."
systemctl stop postgresql 2>/dev/null || true
sleep 2

# Ensure old cluster is really down
if pgrep -f "postgres -D $OLD_DATADIR" >/dev/null 2>&1; then
    ERROR "Old PostgreSQL cluster still running; aborting."
fi

INFO "Creating new cluster directory and initializing..."
mkdir -p "$NEW_DATADIR"
chown postgres:postgres "$NEW_DATADIR"
chmod 700 "$NEW_DATADIR"
sudo -u postgres "$NEW_BIN/initdb" -D "$NEW_DATADIR" -E UTF8 --locale=en_US.UTF-8 || ERROR "initdb failed"

INFO "Running pg_upgrade --check (dry run)..."
sudo -u postgres "$NEW_BIN/pg_upgrade" \
    -b "$OLD_BIN" -B "$NEW_BIN" \
    -d "$OLD_DATADIR" -D "$NEW_DATADIR" \
    --check -U postgres || ERROR "pg_upgrade --check failed"

INFO "Running pg_upgrade (actual migration)..."
sudo -u postgres "$NEW_BIN/pg_upgrade" \
    -b "$OLD_BIN" -B "$NEW_BIN" \
    -d "$OLD_DATADIR" -D "$NEW_DATADIR" \
    -U postgres -k || ERROR "pg_upgrade failed"

# Copy config from old cluster and fix paths for new version
INFO "Copying and adjusting configuration..."
cp -a "$OLD_DATADIR/pg_hba.conf" "$NEW_DATADIR/"
cp -a "$OLD_DATADIR/postgresql.conf" "$NEW_DATADIR/"
sed -i "s|/${OLD_VER}/|/${NEW_VER}/|g" "$NEW_DATADIR/postgresql.conf"
[ -d "$OLD_DATADIR/conf.d" ] && cp -a "$OLD_DATADIR/conf.d" "$NEW_DATADIR/" && chown -R postgres:postgres "$NEW_DATADIR/conf.d"

# Point systemd unit at new version
if [ -f /etc/systemd/system/postgresql.service ]; then
    INFO "Updating systemd unit to PostgreSQL ${NEW_VER}..."
    sed -i "s/${OLD_VER}/${NEW_VER}/g" /etc/systemd/system/postgresql.service
    systemctl daemon-reload
fi

INFO "Starting PostgreSQL ${NEW_VER}..."
systemctl start postgresql || ERROR "Failed to start postgresql"

INFO "Running ANALYZE on all databases..."
sudo -u postgres "$NEW_BIN/vacuumdb" -a -z 2>/dev/null || true

INFO "Starting dependent services..."
for svc in vaultwarden gogs forgejo freshrss; do
    systemctl start "$svc" 2>/dev/null || true
done

INFO "PostgreSQL 15 → 17 migration complete."
INFO "Old cluster left at $OLD_DATADIR. After verifying apps, remove with: rm -rf $OLD_DATADIR"
echo ""
