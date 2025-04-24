#!/bin/bash
set -e

# Source utilities
source "$(dirname "$0")/config/utils.sh"

# Configuration
INSTALL_DIR="/opt/navidrome"
DATA_DIR="/var/lib/navidrome"
SERVICE_NAME="navidrome"

# Check mode - only verify service
if [ "$1" = "--check" ]; then
    NAVIDROME_BIN="/opt/navidrome/navidrome"
    if [ -f "$NAVIDROME_BIN" ] && [ -x "$NAVIDROME_BIN" ]; then
        VERSION=$($NAVIDROME_BIN --version 2>&1 | grep -oP '\d+\.\d+\.\d+' || echo "unknown")
        if [ -n "$VERSION" ] && [ "$VERSION" != "unknown" ]; then
            log_message "OK - Current version: $VERSION"
            exit 0
        fi
    fi
    log_message "Navidrome not found at $NAVIDROME_BIN or not executable"
    exit 1
fi

# Get current version
CURRENT_VERSION=$($INSTALL_DIR/navidrome --version 2>&1 | head -n1 | cut -d' ' -f3)
if [ -z "$CURRENT_VERSION" ]; then
    log_message "Failed to get current version of Navidrome"
    exit 1
fi
log_message "Current Navidrome version: $CURRENT_VERSION"

# Get latest version from GitHub
LATEST_VERSION=$(curl -s https://api.github.com/repos/navidrome/navidrome/releases/latest | grep -oP '"tag_name": "v\K(.*)(?=")')
if [ -z "$LATEST_VERSION" ]; then
    log_message "Failed to get latest version information"
    exit 1
fi

log_message "Latest available version: $LATEST_VERSION"

if [ "$CURRENT_VERSION" = "$LATEST_VERSION" ]; then
    log_message "Navidrome is already at the latest version"
    exit 0
fi

# Stop service
log_message "Stopping Navidrome service..."
systemctl stop $SERVICE_NAME

# Create backup
log_message "Creating backup..."
backup_create $SERVICE_NAME "$DATA_DIR"
backup_create $SERVICE_NAME "$INSTALL_DIR/navidrome" ".bin"

# Cleanup old backups
log_message "Cleaning up old backups..."
backup_cleanup $SERVICE_NAME

# Update logic here...

# If update fails
if [ $? -ne 0 ]; then
    log_message "Update failed, restoring from backup..."
    backup_restore $SERVICE_NAME "$DATA_DIR"
    systemctl start $SERVICE_NAME
    exit 1
fi

# Start service
log_message "Starting Navidrome service..."
systemctl start $SERVICE_NAME

# Check service status
if ! systemctl is-active --quiet $SERVICE_NAME; then
    log_message "Service failed to start, restoring from backup..."
    backup_restore $SERVICE_NAME "$DATA_DIR"
    systemctl start $SERVICE_NAME
    exit 1
fi

log_message "Update completed successfully!"