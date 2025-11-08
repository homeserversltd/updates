#!/bin/bash

# Migration 00000001: Migrate KEA DHCP CSV files to ramdisk
# 
# This migration moves KEA DHCP lease files from /var/lib/kea/ to /mnt/ramdisk/
# to prevent root filesystem fullness from affecting DHCP operations.
#
# Idempotent: Safe to run multiple times
# Rollback: Restores backup on failure

set +e  # Do not exit on error - we handle errors explicitly

echo "========================================"
echo "Migration 00000001: KEA DHCP to Ramdisk"
echo "========================================"
echo ""

# Configuration
KEA_CONF="/etc/kea/kea-dhcp4.conf"
KEA_CONF_BACKUP="${KEA_CONF}.pre-ramdisk"
KEA_SERVICE="kea-dhcp4-server.service"
APPARMOR_PROFILE="/etc/apparmor.d/usr.sbin.kea-dhcp4"
SYSTEMD_OVERRIDE_DIR="/etc/systemd/system/kea-dhcp4-server.service.d"
SYSTEMD_OVERRIDE="${SYSTEMD_OVERRIDE_DIR}/ramdisk.conf"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "ERROR: This migration must run as root"
    exit 1
fi

# Function to log with timestamp
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Function to handle errors
error_exit() {
    log "ERROR: $1"
    
    # Attempt to restore backup if it exists
    if [ -f "$KEA_CONF_BACKUP" ]; then
        log "Attempting to restore backup configuration..."
        cp "$KEA_CONF_BACKUP" "$KEA_CONF"
        systemctl restart "$KEA_SERVICE" 2>/dev/null
        log "Backup restored"
    fi
    
    exit 1
}

# IDEMPOTENCY CHECK: Is KEA already using ramdisk?
log "Checking if KEA is already using ramdisk..."
if [ -f "$KEA_CONF" ]; then
    if grep -q '"/mnt/ramdisk/kea-leases4.csv"' "$KEA_CONF"; then
        log "SUCCESS: KEA is already configured to use ramdisk"
        log "Migration already applied, exiting successfully"
        exit 0
    fi
fi

# Deploy AppArmor profile to allow ramdisk access
log "Deploying AppArmor profile..."
if [ ! -f "/usr/share/kea/apparmor/kea-dhcp4.apparmor" ]; then
    log "WARNING: AppArmor source profile not found, using embedded profile"
    cat > "$APPARMOR_PROFILE" << 'APPARMOR_EOF'
abi <abi/3.0>,

include <tunables/global>

profile kea-dhcp4 /usr/sbin/kea-dhcp4 {
  include <abstractions/base>
  include <abstractions/nameservice>
  include <abstractions/mysql>
  include <abstractions/openssl>

  capability net_bind_service,
  capability net_raw,

  network inet dgram,
  network inet stream,
  network netlink raw,
  network packet raw,

  /etc/gss/mech.d/ r,
  /etc/gss/mech.d/* r,
  /etc/kea/ r,
  /etc/kea/** r,
  /usr/sbin/kea-dhcp4 mr,
  /usr/sbin/kea-lfc Px,

  owner /run/kea/kea-dhcp4.kea-dhcp4.pid w,
  owner /run/lock/kea/logger_lockfile rwk,
  owner /{tmp,run/kea}/kea4-ctrl-socket w,
  owner /{tmp,run/kea}/kea4-ctrl-socket.lock rwk,

  # Lease files in default location
  owner /var/lib/kea/kea-leases4.csv rw,
  owner /var/lib/kea/kea-leases4.csv2 rw,

  # Lease files in ramdisk
  owner /mnt/ramdisk/kea-leases4.csv rw,
  owner /mnt/ramdisk/kea-leases4.csv2 rw,

  owner /var/log/kea/kea-dhcp4.log rw,
  owner /var/log/kea/kea-dhcp4.log.[0-9]* rw,
  owner /var/log/kea/kea-dhcp4.log.lock rwk,
}
APPARMOR_EOF
fi

if [ -f "$APPARMOR_PROFILE" ]; then
    if apparmor_parser -r "$APPARMOR_PROFILE" 2>&1; then
        log "AppArmor profile loaded successfully"
    else
        log "WARNING: Failed to load AppArmor profile (may not be critical)"
    fi
fi

# Deploy systemd override to create CSV files on boot
log "Deploying systemd override for ramdisk CSV creation..."
mkdir -p "$SYSTEMD_OVERRIDE_DIR"
cat > "$SYSTEMD_OVERRIDE" << 'OVERRIDE_EOF'
[Unit]
RequiresMountsFor=/mnt/ramdisk
After=mnt-ramdisk.mount

[Service]
# Ensure KEA lease files exist before KEA tries to open them
# Ramdisk is volatile, so files must be recreated on each boot
ExecStartPre=/bin/sh -c '/usr/bin/touch /mnt/ramdisk/kea-leases4.csv && /usr/bin/chown _kea:_kea /mnt/ramdisk/kea-leases4.csv'
ExecStartPre=/bin/sh -c '/usr/bin/touch /mnt/ramdisk/kea-leases4.csv2 && /usr/bin/chown _kea:_kea /mnt/ramdisk/kea-leases4.csv2'
OVERRIDE_EOF

if [ -f "$SYSTEMD_OVERRIDE" ]; then
    log "Systemd override deployed"
    systemctl daemon-reload
    log "Systemd configuration reloaded"
else
    error_exit "Failed to create systemd override"
fi

# Backup current KEA configuration
log "Backing up current KEA configuration..."
if [ -f "$KEA_CONF" ]; then
    if ! cp "$KEA_CONF" "$KEA_CONF_BACKUP"; then
        error_exit "Failed to create backup of KEA configuration"
    fi
    log "Configuration backed up to $KEA_CONF_BACKUP"
else
    error_exit "KEA configuration file not found at $KEA_CONF"
fi

# Create initial CSV files in ramdisk
log "Creating initial CSV files in ramdisk..."
touch /mnt/ramdisk/kea-leases4.csv
touch /mnt/ramdisk/kea-leases4.csv2
chown _kea:_kea /mnt/ramdisk/kea-leases4.csv*
chmod 644 /mnt/ramdisk/kea-leases4.csv*
log "CSV files created with proper ownership"

# Update KEA configuration to use ramdisk
log "Updating KEA configuration to use ramdisk..."

# Use Python to modify the JSON config safely
python3 << EOF
import json
import sys

try:
    with open('$KEA_CONF', 'r') as f:
        config = json.load(f)
    
    # Update lease-database configuration to use memfile on ramdisk
    if 'Dhcp4' in config:
        config['Dhcp4']['lease-database'] = {
            'type': 'memfile',
            'persist': True,
            'name': '/mnt/ramdisk/kea-leases4.csv',
            'lfc-interval': 3600
        }
        
        # Write updated config
        with open('$KEA_CONF', 'w') as f:
            json.dump(config, f, indent=4)
        
        print("Configuration updated successfully")
        sys.exit(0)
    else:
        print("ERROR: Invalid KEA configuration structure")
        sys.exit(1)
        
except Exception as e:
    print(f"ERROR: Failed to update configuration: {e}")
    sys.exit(1)
EOF

if [ $? -ne 0 ]; then
    error_exit "Failed to update KEA configuration"
fi

log "Configuration updated successfully"

# Set proper permissions
chmod 640 "$KEA_CONF"
chown root:_kea "$KEA_CONF" 2>/dev/null || chown root:kea "$KEA_CONF" 2>/dev/null || true

# Restart KEA service
log "Restarting KEA DHCP service..."
if ! systemctl restart "$KEA_SERVICE"; then
    error_exit "Failed to restart KEA service"
fi

# Wait for service to stabilize
sleep 2

# Verify service is running
if ! systemctl is-active --quiet "$KEA_SERVICE"; then
    error_exit "KEA service failed to start after configuration change"
fi

log "KEA service restarted and running successfully"

# Verify ramdisk files are accessible
log "Verifying ramdisk files exist and are accessible..."
if [ -f "/mnt/ramdisk/kea-leases4.csv" ] && [ -f "/mnt/ramdisk/kea-leases4.csv2" ]; then
    log "Ramdisk CSV files verified"
else
    error_exit "Failed to create ramdisk CSV files"
fi

# Success
log ""
log "========================================"
log "SUCCESS: Migration completed"
log "========================================"
log ""
log "KEA DHCP lease files moved to ramdisk at /mnt/ramdisk/"
log "AppArmor profile updated to allow ramdisk access"
log "Systemd override configured to recreate files on boot"
log "Backup configuration saved at: $KEA_CONF_BACKUP"
log ""
log "Network DHCP will continue operating normally"
log ""

exit 0

