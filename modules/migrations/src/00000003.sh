#!/bin/bash

# Migration 00000003: Update Mount NAS Service Configuration
# 
# This migration updates the mountNas.service to use the new configuration
# with vault dependencies and proper ordering. This ensures the NAS mount
# service properly depends on the vault being mounted first.
#
# Idempotent: Safe to run multiple times
# Target: All systems with NAS mounting capability

set +e  # Do not exit on error - we handle errors explicitly

echo "========================================"
echo "Migration 00000003: Mount NAS Service Update"
echo "========================================"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "ERROR: This migration must run as root"
    exit 1
fi

# Function to log with timestamp
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Configuration
SERVICE_FILE="/etc/systemd/system/mountNas.service"
SERVICE_BACKUP="${SERVICE_FILE}.pre-migration-$(date +%s)"

# Desired service file content (new configuration with vault dependencies)
DESIRED_CONTENT='[Unit]
Description=NAS Mount Status
ConditionPathExists=/vault/scripts/init.sh
ConditionPathIsMountPoint=/vault
Requires=vault.mount
After=vault.mount

[Service]
Type=oneshot
ExecStart=/vault/scripts/init.sh
StandardOutput=journal
StandardError=journal
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target'

# IDEMPOTENCY CHECK: Does service file already match desired state?
log "Checking if Mount NAS service already matches desired state..."
if [ -f "$SERVICE_FILE" ]; then
    if diff -q <(echo "$DESIRED_CONTENT") "$SERVICE_FILE" >/dev/null 2>&1; then
        log "SUCCESS: Service file already matches desired state"
        log "Migration already applied, exiting successfully"
        exit 0
    else
        log "Service file exists but needs update"
    fi
else
    log "Service file does not exist, will create it"
fi

# Stop the service if it's running (since we're changing configuration)
log "Checking if Mount NAS service is running..."
if systemctl is-active --quiet mountNas.service 2>/dev/null; then
    log "Mount NAS service is running, stopping it"
    if systemctl stop mountNas.service 2>/dev/null; then
        log "Mount NAS service stopped successfully"
    else
        log "WARNING: Could not stop Mount NAS service, continuing anyway"
    fi
else
    log "Mount NAS service is not running"
fi

# Create backup of existing service file
if [ -f "$SERVICE_FILE" ]; then
    log "Creating backup of existing service file: $SERVICE_BACKUP"
    if cp "$SERVICE_FILE" "$SERVICE_BACKUP"; then
        log "Backup created successfully"
    else
        log "ERROR: Failed to create backup"
        exit 1
    fi
else
    log "No existing service file to backup"
fi

# Write the desired content to the service file
log "Writing new service file configuration..."
if echo "$DESIRED_CONTENT" > "$SERVICE_FILE"; then
    log "Service file updated successfully"
else
    log "ERROR: Failed to update service file"
    # Restore backup if update failed
    if [ -f "$SERVICE_BACKUP" ]; then
        cp "$SERVICE_BACKUP" "$SERVICE_FILE"
        log "Restored backup after failure"
    fi
    exit 1
fi

# Verify the updated service file
log "Verifying updated service file..."
if [ ! -f "$SERVICE_FILE" ]; then
    log "ERROR: Service file does not exist after update"
    exit 1
fi

# Verify content matches desired state
if ! diff -q <(echo "$DESIRED_CONTENT") "$SERVICE_FILE" >/dev/null 2>&1; then
    log "ERROR: Service file does not match desired state after update"
    exit 1
fi

# Verify it's a valid systemd unit
if systemd-analyze verify "$SERVICE_FILE" >/dev/null 2>&1; then
    log "Service file is valid systemd unit"
else
    log "WARNING: Service file validation failed, but file was written correctly"
fi

# Reload systemd to recognize the changes
log "Reloading systemd daemon..."
if systemctl daemon-reload; then
    log "Systemd daemon reloaded successfully"
else
    log "WARNING: Failed to reload systemd daemon"
fi

# Success
log ""
log "========================================"
log "SUCCESS: Migration completed"
log "========================================"
log ""
log "Mount NAS service updated with vault dependencies"
log "Service file: $SERVICE_FILE"
log "Backup saved at: $SERVICE_BACKUP"
log ""

exit 0

