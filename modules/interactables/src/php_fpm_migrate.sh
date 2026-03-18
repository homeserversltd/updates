#!/bin/bash
# Interactable: Migrate PHP-FPM pool configs and systemd units to the default PHP version.
# After a distro upgrade (e.g. Debian 12→13) the default PHP may be newer; pool configs
# and units can still point at the old version. This script detects current (in-use) and
# default (new) PHP versions at runtime and migrates without hardcoding version numbers.
# WARNING: Can fuck your shit up. Backup and run at your own risk. Only shown after Debian 12→13.
set -e

LOG_FILE="${LOG_FILE:-/var/log/homeserver/migrations.log}"
ID="php_fpm_migrate"
KNOWN_POOLS="piwigo ampache freshrss"

INFO()  { echo "$ID: $*" | tee -a "$LOG_FILE"; }
WARN()  { echo "$ID WARNING: $*" | tee -a "$LOG_FILE" >&2; }
ERROR() { echo "$ID ERROR: $*" | tee -a "$LOG_FILE" >&2; exit 1; }

if [ "$EUID" -ne 0 ]; then
    ERROR "Must run as root"
fi

# Detect "new" PHP version: default CLI PHP (what the distro provides after upgrade)
if ! command -v php >/dev/null 2>&1; then
    ERROR "Default php not found. Install the default PHP package."
fi
NEW_VER=$(php -r "echo PHP_MAJOR_VERSION.'.'.PHP_MINOR_VERSION;" 2>/dev/null || true)
if [ -z "$NEW_VER" ]; then
    ERROR "Could not detect default PHP version (php -r ... failed)."
fi

# Detect "old" PHP version: find which /etc/php/*/fpm/pool.d has our known pool configs
OLD_VER=""
for dir in /etc/php/*/fpm/pool.d; do
    [ -d "$dir" ] || continue
    for name in $KNOWN_POOLS; do
        if [ -f "$dir/${name}.conf" ]; then
            # dir is /etc/php/X.Y/fpm/pool.d; extract X.Y
            OLD_VER=$(echo "$dir" | sed -n 's|/etc/php/\([^/]*\)/fpm/pool.d|\1|p')
            break 2
        fi
    done
done

if [ -z "$OLD_VER" ]; then
    ERROR "No known PHP-FPM pool configs (${KNOWN_POOLS}) found under any /etc/php/*/fpm/pool.d. Nothing to migrate."
fi

if [ "$OLD_VER" = "$NEW_VER" ]; then
    ERROR "Default PHP is already ${NEW_VER}; pool configs are already under that version. Nothing to migrate."
fi

POOL_SRC="/etc/php/${OLD_VER}/fpm/pool.d"
POOL_DST="/etc/php/${NEW_VER}/fpm/pool.d"

echo ""
echo "=============================================="
echo "  PHP-FPM MIGRATION: ${OLD_VER} → ${NEW_VER}"
echo "=============================================="
echo ""
echo "  *** THIS CAN FUCK YOUR SHIT UP ***"
echo ""
echo "  - PHP-FPM services (Piwigo, Ampache, FreshRSS) will be restarted."
echo "  - Pool configs will be copied to PHP ${NEW_VER}; systemd units updated."
echo "  - Old PHP ${OLD_VER} remains installed until you remove it (after verifying)."
echo ""
echo "=============================================="
echo ""

# New PHP FPM must be available (install if missing)
if ! command -v "php-fpm${NEW_VER}" >/dev/null 2>&1; then
    INFO "PHP ${NEW_VER} FPM not installed; installing php${NEW_VER}-fpm..."
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq && apt-get install -y -qq "php${NEW_VER}-fpm" || ERROR "Failed to install php${NEW_VER}-fpm"
fi
if [ ! -d "$POOL_DST" ]; then
    ERROR "PHP ${NEW_VER} pool.d not found at $POOL_DST after install."
fi

# Copy known pool configs from old to new (only if they exist)
COPIED=0
for name in $KNOWN_POOLS; do
    if [ -f "$POOL_SRC/${name}.conf" ]; then
        cp -a "$POOL_SRC/${name}.conf" "$POOL_DST/${name}.conf"
        INFO "Copied pool ${name}.conf to PHP ${NEW_VER}"
        COPIED=$((COPIED + 1))
    fi
done
if [ "$COPIED" -eq 0 ]; then
    WARN "No known pool configs found in $POOL_SRC; nothing copied."
fi

# Update systemd units that reference the old PHP version (any unit under system that mentions old ver)
for unit in /etc/systemd/system/piwigo.service; do
    if [ -f "$unit" ] && grep -q "${OLD_VER}\|php-fpm${OLD_VER}" "$unit" 2>/dev/null; then
        sed -i "s/${OLD_VER}/${NEW_VER}/g; s/php-fpm${OLD_VER}/php-fpm${NEW_VER}/g" "$unit"
        INFO "Updated $unit to PHP ${NEW_VER}"
        systemctl daemon-reload
    fi
done

# Restart new PHP FPM and Piwigo (standalone pool)
INFO "Restarting php${NEW_VER}-fpm..."
systemctl restart "php${NEW_VER}-fpm" || ERROR "Failed to restart php${NEW_VER}-fpm"
if systemctl is-enabled piwigo.service >/dev/null 2>&1; then
    INFO "Restarting piwigo.service..."
    systemctl restart piwigo.service || WARN "piwigo.service restart failed (may be expected if not used)"
fi

INFO "PHP-FPM migration complete (${OLD_VER} → ${NEW_VER})."
INFO "Old PHP ${OLD_VER} configs remain at $POOL_SRC. After verifying, you can remove php${OLD_VER}-fpm if desired."
echo ""
