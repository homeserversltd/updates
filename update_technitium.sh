#!/bin/bash
set -e

# Source utilities
source "$(dirname "$0")/config/utils.sh"

# Configuration
SERVICE_NAME="technitium"
SERVER="localhost:5380"
CONFIG_DIR="/etc/technitium"
DATA_DIR="/var/lib/technitium"

# Check mode - only verify service
if [ "$1" = "--check" ]; then
    if systemctl is-active --quiet technitium; then
        VERSION=$(curl -s "http://$SERVER/api/user/version" | jq -r '.response.version')
        if [ -n "$VERSION" ] && [ "$VERSION" != "null" ]; then
            log_message "OK - Current version: $VERSION"
            exit 0
        fi
    fi
    log_message "Technitium DNS Server not running or not responding"
    exit 1
fi

log_message "Checking Technitium DNS Server for updates..."

# Get current version
CURRENT_VERSION=$(curl -s "http://$SERVER/api/user/version" | jq -r '.response.version')
if [ -z "$CURRENT_VERSION" ] || [ "$CURRENT_VERSION" == "null" ]; then
    log_message "Failed to get current version"
    exit 1
fi
log_message "Current version: $CURRENT_VERSION"

# Step 1: Login and get session token
log_message "Logging in to Technitium DNS Server..."
RESPONSE=$(curl -s -X POST "http://$SERVER/api/user/login?user=$USERNAME&pass=$PASSWORD")
STATUS=$(echo $RESPONSE | jq -r '.status')

if [ "$STATUS" != "ok" ]; then
    log_message "Login failed"
    exit 1
fi

TOKEN=$(echo $RESPONSE | jq -r '.token')
if [ "$TOKEN" == "null" ]; then
    log_message "Failed to obtain token"
    exit 1
fi
log_message "Successfully logged in"

# Step 2: Check for update
log_message "Checking for available updates..."
UPDATE_RESPONSE=$(curl -s -X GET "http://$SERVER/api/user/checkForUpdate?token=$TOKEN")
UPDATE_CHECK=$(echo $UPDATE_RESPONSE | jq -r '.response.updateAvailable')
UPDATE_STATUS=$(echo $UPDATE_RESPONSE | jq -r '.status')
LATEST_VERSION=$(echo $UPDATE_RESPONSE | jq -r '.response.version')

if [ "$UPDATE_STATUS" != "ok" ]; then
    log_message "Failed to check for updates"
    exit 1
fi

log_message "Latest available version: $LATEST_VERSION"

# Step 3: Conditionally apply update
if [ "$UPDATE_CHECK" = "true" ]; then
    log_message "Update available. Creating backup..."
    
    # Stop service
    systemctl stop $SERVICE_NAME
    
    # Backup configuration and data
    backup_create $SERVICE_NAME "$CONFIG_DIR"
    backup_create $SERVICE_NAME "$DATA_DIR"
    
    # Cleanup old backups
    backup_cleanup $SERVICE_NAME
    
    log_message "Installing update..."
    if ! curl -sSL https://download.technitium.com/dns/install.sh | sudo bash; then
        log_message "Update failed, restoring from backup..."
        backup_restore $SERVICE_NAME "$CONFIG_DIR"
        backup_restore $SERVICE_NAME "$DATA_DIR"
        systemctl start $SERVICE_NAME
        exit 1
    fi
    
    # Start service
    systemctl start $SERVICE_NAME
    
    # Check service status
    if ! systemctl is-active --quiet $SERVICE_NAME; then
        log_message "Service failed to start, restoring from backup..."
        backup_restore $SERVICE_NAME "$CONFIG_DIR"
        backup_restore $SERVICE_NAME "$DATA_DIR"
        systemctl start $SERVICE_NAME
        exit 1
    fi
    
    log_message "Successfully updated Technitium DNS Server to version $LATEST_VERSION"
else
    log_message "No updates available"
fi

# Step 4: Logout
log_message "Logging out..."
LOGOUT_RESPONSE=$(curl -s -X POST "http://$SERVER/api/user/logout?token=$TOKEN")
LOGOUT_STATUS=$(echo $LOGOUT_RESPONSE | jq -r '.status')

if [ "$LOGOUT_STATUS" != "ok" ]; then
    log_message "Logout failed"
    exit 1
fi

log_message "Update check completed successfully"
exit 0
