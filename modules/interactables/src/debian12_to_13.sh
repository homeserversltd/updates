#!/bin/bash
# Interactive migration: Debian 12 (Bookworm) → 13 (Trixie) in-place upgrade.
# Only presented when lsb_release -cs = bookworm. Backs up APT sources, switches
# suite to trixie, removes bookworm-backports, runs apt full-upgrade, adds trixie-backports.
# Reboot required after run. Third-party keyrings (Jellyfin, Tailscale, Microsoft, Caddy)
# may need manual refresh after upgrade; see docs/memories/ongoing/debian12to13.
set -e

LOG_FILE="/var/log/homeserver/migrations.log"
ID="debian12_to_13"
BACKUP_DIR="/var/backups/debian12_to_13"
SOURCES_LIST="/etc/apt/sources.list"
SOURCES_D="/etc/apt/sources.list.d"

INFO()  { echo "$ID: $*" | tee -a "$LOG_FILE"; }
WARN()  { echo "$ID WARNING: $*" | tee -a "$LOG_FILE" >&2; }
ERROR() { echo "$ID ERROR: $*" | tee -a "$LOG_FILE" >&2; exit 1; }

if [ "$EUID" -ne 0 ]; then
    ERROR "Must run as root"
fi

CURRENT=$(/usr/bin/lsb_release -cs 2>/dev/null || true)
if [ "$CURRENT" != "bookworm" ]; then
    ERROR "This migration is for Debian 12 (bookworm) only. Current codename: ${CURRENT:-unknown}"
fi

INFO "Starting Debian 12 → 13 in-place upgrade"

# 1) Backup APT sources
mkdir -p "$BACKUP_DIR"
TIMESTAMP=$(date +%Y%m%d%H%M%S)
cp -a "$SOURCES_LIST" "$BACKUP_DIR/sources.list.$TIMESTAMP"
for f in "$SOURCES_D"/*.list "$SOURCES_D"/*.sources 2>/dev/null; do
    [ -f "$f" ] || continue
    cp -a "$f" "$BACKUP_DIR/$(basename "$f").$TIMESTAMP"
done
INFO "Backed up APT sources to $BACKUP_DIR"

# 2) Remove bookworm-backports (and sloppy) so APT does not complain
for f in "$SOURCES_D"/bookworm-backports*.list "$SOURCES_D"/bookworm-backports*.sources 2>/dev/null; do
    [ -f "$f" ] || continue
    rm -f "$f"
    INFO "Removed $f"
done

# 3) Replace bookworm with trixie in main list
if [ -f "$SOURCES_LIST" ]; then
    sed -i 's/bookworm/trixie/g' "$SOURCES_LIST"
    INFO "Updated $SOURCES_LIST bookworm → trixie"
fi

# 4) Replace in known .list files that use codename (jellyfin, etc.)
for f in "$SOURCES_D"/*.list; do
    [ -f "$f" ] || continue
    if grep -q bookworm "$f" 2>/dev/null; then
        sed -i 's/bookworm/trixie/g' "$f"
        INFO "Updated $f bookworm → trixie"
    fi
done
for f in "$SOURCES_D"/*.sources; do
    [ -f "$f" ] || continue
    if grep -q bookworm "$f" 2>/dev/null; then
        sed -i 's/bookworm/trixie/g' "$f"
        INFO "Updated $f bookworm → trixie"
    fi
done

# 5) apt update and full-upgrade
export DEBIAN_FRONTEND=noninteractive
INFO "Running apt update"
apt-get update -y || ERROR "apt update failed"
INFO "Running apt full-upgrade (may take several minutes)"
apt-get full-upgrade -y || ERROR "apt full-upgrade failed"

# 6) Add trixie-backports
echo "deb http://deb.debian.org/debian trixie-backports main" > "$SOURCES_D/trixie-backports.list"
INFO "Added trixie-backports"
apt-get update -y || true

# 7) Cleanup
apt-get autoremove -y || true
apt-get autoclean || true

INFO "Debian 12 → 13 upgrade step completed. REBOOT REQUIRED (new kernel)."
echo ""
echo "debian12_to_13: REBOOT REQUIRED. Run: sudo reboot"
echo ""
