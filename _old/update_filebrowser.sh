#!/bin/bash
set -e

# Source utilities
source "$(dirname "$0")/config/utils.sh"

# Configuration
SERVICE_NAME="filebrowser"
DB_PATH="/etc/filebrowser/filebrowser.db"
DATA_DIR="/etc/filebrowser"

# Check mode - only verify service
if [ "$1" = "--check" ]; then
    if [ -f "/usr/local/bin/filebrowser" ] && [ -x "/usr/local/bin/filebrowser" ]; then
        # Try different version formats
        VERSION=$(filebrowser version 2>&1 | grep -oP 'v\K\d+\.\d+\.\d+' || echo "unknown")
        if [ "$VERSION" = "unknown" ]; then
            # Try alternate format
            VERSION=$(filebrowser version 2>&1 | awk '/File Browser/ {print $2}' | sed 's/v//')
        fi
        if [ -n "$VERSION" ] && [ "$VERSION" != "unknown" ]; then
            log_message "OK - Current version: $VERSION"
            exit 0
        fi
    fi
    log_message "Filebrowser not found at /usr/local/bin/filebrowser or not executable"
    exit 1
fi

# Get current version
CURRENT_VERSION=$(filebrowser --version 2>&1 | head -n1 | cut -d' ' -f3)
if [ -z "$CURRENT_VERSION" ]; then
    log_message "Failed to get current version of Filebrowser"
    exit 1
fi
log_message "Current Filebrowser version: $CURRENT_VERSION"

# Get latest version from GitHub
LATEST_VERSION=$(curl -s https://api.github.com/repos/filebrowser/filebrowser/releases/latest | grep -oP '"tag_name": "v\K(.*)(?=")')
if [ -z "$LATEST_VERSION" ]; then
    log_message "Failed to get latest version information"
    exit 1
fi
log_message "Latest available version: $LATEST_VERSION"

if [ "$CURRENT_VERSION" = "$LATEST_VERSION" ]; then
    log_message "Filebrowser is already at the latest version"
    exit 0
fi

log_message "Stopping Filebrowser service..."
systemctl stop $SERVICE_NAME

# Create backup
log_message "Creating backup..."
backup_create $SERVICE_NAME "$DB_PATH" ".db"
backup_create $SERVICE_NAME "$DATA_DIR/settings.json" ".json"

# Cleanup old backups
log_message "Cleaning up old backups..."
backup_cleanup $SERVICE_NAME

# Update Filebrowser
log_message "Updating Filebrowser..."
if ! curl -fsSL https://raw.githubusercontent.com/filebrowser/get/master/get.sh | bash; then
    log_message "Update failed, restoring from backup..."
    backup_restore $SERVICE_NAME "$DB_PATH"
    backup_restore $SERVICE_NAME "$DATA_DIR/settings.json"
    systemctl start $SERVICE_NAME
    exit 1
fi

# Start service
log_message "Starting Filebrowser service..."
systemctl start $SERVICE_NAME

# Wait for service to start
sleep 5

# Check service status
if ! systemctl is-active --quiet $SERVICE_NAME; then
    log_message "Service failed to start, restoring from backup..."
    backup_restore $SERVICE_NAME "$DB_PATH"
    backup_restore $SERVICE_NAME "$DATA_DIR/settings.json"
    systemctl start $SERVICE_NAME
    exit 1
fi

log_message "Update completed successfully!"
log_message "New version: $(filebrowser --version 2>&1 | head -n1)"
systemctl status $SERVICE_NAME
exit 0