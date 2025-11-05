#!/bin/bash

# Migration 00000004: Remove NAS Dependency from Filebrowser Service
# 
# This migration removes the NAS dependency from filebrowser.service to ensure
# Filebrowser can start independently without requiring NAS to be mounted.
# This fixes installations where Filebrowser was incorrectly configured with
# NAS dependencies.
#
# Idempotent: Safe to run multiple times
# Conditional: Only applies to systems with filebrowser installed

set +e  # Do not exit on error - we handle errors explicitly

echo "========================================"
echo "Migration 00000004: Filebrowser Service Fix"
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
SERVICE_FILE="/etc/systemd/system/filebrowser.service"
SERVICE_BACKUP="${SERVICE_FILE}.pre-migration-$(date +%s)"

# Desired service file content (without NAS dependency)
DESIRED_CONTENT='[Unit]
Description=File Browser
After=network.target 

[Service]
Type=simple
User=filebrowser
Group=filebrowser
ExecStart=/usr/local/bin/filebrowser -d /etc/filebrowser/filebrowser.db
WorkingDirectory=/etc/filebrowser
Restart=on-failure
RestartSec=5
StartLimitInterval=60s
StartLimitBurst=3

[Install]
WantedBy=multi-user.target'

# IDEMPOTENCY CHECK 1: Does filebrowser service exist?
log "Checking if filebrowser service exists..."
if [ ! -f "$SERVICE_FILE" ]; then
    log "SUCCESS: Filebrowser service not installed on this system"
    log "Migration not applicable, exiting successfully"
    exit 0
fi

log "Filebrowser service found: $SERVICE_FILE"

# IDEMPOTENCY CHECK 2: Does service already match desired state?
log "Checking if service already matches desired state..."
if diff -q <(echo "$DESIRED_CONTENT") "$SERVICE_FILE" >/dev/null 2>&1; then
    log "SUCCESS: Service file already matches desired state"
    log "Migration already applied, exiting successfully"
    exit 0
fi

log "Service file needs update"

# Check if service has NAS dependency (just for logging purposes)
if grep -q "ExecStartPre=.*test.*mnt/nas" "$SERVICE_FILE"; then
    log "Detected NAS dependency in service file (will be removed)"
else
    log "Updating service file to ensure correct configuration"
fi

# Create backup of existing service file
log "Creating backup of existing service file: $SERVICE_BACKUP"
if ! cp "$SERVICE_FILE" "$SERVICE_BACKUP"; then
    log "ERROR: Failed to create backup"
    exit 1
fi
log "Backup created successfully"

# Write the desired content to the service file
log "Updating filebrowser.service..."
if ! echo "$DESIRED_CONTENT" > "$SERVICE_FILE"; then
    log "ERROR: Failed to update service file"
    # Restore backup
    cp "$SERVICE_BACKUP" "$SERVICE_FILE"
    log "Restored backup after failure"
    exit 1
fi

log "Service file updated successfully"

# Verify the updated service file
log "Verifying updated service file..."

# Check if file exists
if [ ! -f "$SERVICE_FILE" ]; then
    log "ERROR: Service file does not exist after update"
    exit 1
fi

# Check if content matches desired state
if ! diff -q <(echo "$DESIRED_CONTENT") "$SERVICE_FILE" >/dev/null 2>&1; then
    log "ERROR: Service file does not match desired state after update"
    exit 1
fi

# Verify it's a valid systemd unit
if systemd-analyze verify "$SERVICE_FILE" >/dev/null 2>&1; then
    log "Service file is valid systemd unit"
else
    log "WARNING: Service file validation had issues, but file was written correctly"
fi

# Verify NAS dependency was removed (if it existed)
if grep -q "ExecStartPre=.*test.*mnt/nas" "$SERVICE_FILE"; then
    log "ERROR: NAS dependency still present in service file"
    exit 1
else
    log "NAS dependency successfully removed (if it existed)"
fi

# Reload systemd daemon
log "Reloading systemd daemon..."
if ! systemctl daemon-reload; then
    log "WARNING: Failed to reload systemd daemon"
fi

# Restart filebrowser service if it was running
log "Checking if filebrowser service is active..."
if systemctl is-active --quiet filebrowser.service 2>/dev/null; then
    log "Filebrowser service is running, restarting it..."
    if systemctl restart filebrowser.service; then
        log "Filebrowser service restarted successfully"
        
        # Wait for service to stabilize
        sleep 3
        
        if systemctl is-active --quiet filebrowser.service; then
            log "Filebrowser service is running and healthy"
        else
            log "WARNING: Filebrowser service may not have started properly"
        fi
    else
        log "WARNING: Failed to restart filebrowser service (may need manual restart)"
    fi
else
    log "Filebrowser service is not running (no restart needed)"
fi

# Success
log ""
log "========================================"
log "SUCCESS: Migration completed"
log "========================================"
log ""
log "Filebrowser service updated to remove NAS dependency"
log "Service file: $SERVICE_FILE"
log "Backup saved at: $SERVICE_BACKUP"
log ""

exit 0

