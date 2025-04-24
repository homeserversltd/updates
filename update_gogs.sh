#!/bin/bash
set -e

# Source utilities
source "$(dirname "$0")/config/utils.sh"

# Configuration
SERVICE_NAME="gogs"
INSTALL_DIR="/opt/gogs"
DATA_DIR="/mnt/nas/git"
CONFIG_FILE="/opt/gogs/custom/conf/app.ini"

# Check mode - only verify service
if [ "$1" = "--check" ]; then
    if [ -f "$INSTALL_DIR/gogs" ]; then
        VERSION=$($INSTALL_DIR/gogs --version 2>&1 | cut -d' ' -f3)
        if [ -n "$VERSION" ]; then
            log_message "OK - Current version: $VERSION"
            exit 0
        fi
    fi
    log_message "Gogs binary not found or not executable"
    exit 1
fi

# Get current version
CURRENT_VERSION=$($INSTALL_DIR/gogs --version 2>&1 | cut -d' ' -f3)
if [ -z "$CURRENT_VERSION" ]; then
    log_message "Failed to get current version of Gogs"
    exit 1
fi
log_message "Current Gogs version: $CURRENT_VERSION"

# Get latest version from GitHub API
LATEST_VERSION=$(curl -s https://api.github.com/repos/gogs/gogs/releases/latest | grep -oP '"tag_name": "v\K(.*)(?=")')
if [ -z "$LATEST_VERSION" ]; then
    log_message "Failed to get latest version information"
    exit 1
fi

log_message "Latest available version: $LATEST_VERSION"

if [ "$CURRENT_VERSION" = "$LATEST_VERSION" ]; then
    log_message "Gogs is already at the latest version"
    exit 0
fi

# Stop service
log_message "Stopping Gogs service..."
systemctl stop $SERVICE_NAME

# Create backups
log_message "Creating backups..."
backup_create $SERVICE_NAME "$CONFIG_FILE" ".ini"
backup_create $SERVICE_NAME "$DATA_DIR/repositories" ".tar.gz"
pg_dump -U git gogs > "/tmp/gogs_db.sql"
backup_create $SERVICE_NAME "/tmp/gogs_db.sql" ".sql"
rm "/tmp/gogs_db.sql"

# Cleanup old backups
log_message "Cleaning up old backups..."
backup_cleanup $SERVICE_NAME

# Download and install new version
log_message "Downloading Gogs $LATEST_VERSION..."
if ! wget -q "https://dl.gogs.io/$LATEST_VERSION/gogs_${LATEST_VERSION}_linux_amd64.tar.gz" -O /tmp/gogs.tar.gz; then
    log_message "Failed to download new version"
    systemctl start $SERVICE_NAME
    exit 1
fi

# Backup current installation
mv "$INSTALL_DIR" "${INSTALL_DIR}_backup_$(date +%Y%m%d)"

# Extract new version
if ! tar -xzf /tmp/gogs.tar.gz -C /opt/; then
    log_message "Failed to extract new version, restoring from backup..."
    rm -rf "$INSTALL_DIR"
    mv "${INSTALL_DIR}_backup_$(date +%Y%m%d)" "$INSTALL_DIR"
    systemctl start $SERVICE_NAME
    exit 1
fi

rm /tmp/gogs.tar.gz

# Restore configuration
backup_restore $SERVICE_NAME "$CONFIG_FILE"

# Set permissions
chown -R git:git "$INSTALL_DIR"
chmod -R 750 "$INSTALL_DIR"

# Start service
log_message "Starting Gogs service..."
systemctl start $SERVICE_NAME

# Wait for service to start
sleep 5

# Check service status
if ! systemctl is-active --quiet $SERVICE_NAME; then
    log_message "Service failed to start, restoring from backup..."
    rm -rf "$INSTALL_DIR"
    mv "${INSTALL_DIR}_backup_$(date +%Y%m%d)" "$INSTALL_DIR"
    backup_restore $SERVICE_NAME "$CONFIG_FILE"
    psql -U git gogs < "$BASE_BACKUP_DIR/$SERVICE_NAME/gogs_$(date +%Y%m%d).sql"
    systemctl start $SERVICE_NAME
    exit 1
fi

# Cleanup backup after successful update
rm -rf "${INSTALL_DIR}_backup_$(date +%Y%m%d)"

log_message "Update completed successfully!"
log_message "New version: $($INSTALL_DIR/gogs --version 2>&1 | cut -d' ' -f3)"
systemctl status $SERVICE_NAME
exit 0