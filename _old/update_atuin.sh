#!/bin/bash
set -e

# Source utilities
source "$(dirname "$0")/config/utils.sh"

# Configuration
SERVICE_NAME="atuin"
ADMIN_USER=$(getent passwd 1000 | cut -d: -f1)  # Get admin user by UID 1000
ATUIN_BIN="/home/$ADMIN_USER/.atuin/bin/atuin"  # Updated path to user's home directory

# Check mode - only verify service
if [ "$1" = "--check" ]; then
    if [ -f "$ATUIN_BIN" ] && [ -x "$ATUIN_BIN" ]; then
        VERSION=$($ATUIN_BIN --version 2>/dev/null | awk '{print $2}')
        if [ -n "$VERSION" ]; then
            log_message "OK - Current version: $VERSION"
            exit 0
        fi
    fi
    log_message "Atuin binary not found at $ATUIN_BIN"
    exit 1
fi

# Get current version
CURRENT_VERSION=$($ATUIN_BIN --version 2>/dev/null | awk '{print $2}')
if [ -z "$CURRENT_VERSION" ]; then
    log_message "Failed to get current version of Atuin"
    exit 1
fi
log_message "Current Atuin version: $CURRENT_VERSION"

# Get latest version from GitHub
LATEST_VERSION=$(curl -s https://api.github.com/repos/atuinsh/atuin/releases/latest | grep -oP '"tag_name": "v\K(.*)(?=")')
if [ -z "$LATEST_VERSION" ]; then
    log_message "Failed to get latest version information"
    exit 1
fi

log_message "Latest available version: $LATEST_VERSION"

# Compare versions
if [ "$CURRENT_VERSION" != "$LATEST_VERSION" ]; then
    log_message "Update available. Creating backup..."
    backup_create $SERVICE_NAME "$ATUIN_BIN" ".bin"
    
    log_message "Installing update..."
    # Run the install script as the admin user
    if ! su - "$ADMIN_USER" -c 'bash <(curl --proto "=https" --tlsv1.2 -sSf https://setup.atuin.sh)'; then
        log_message "Failed to update Atuin"
        log_message "Restoring from backup..."
        backup_restore $SERVICE_NAME "$ATUIN_BIN"
        exit 1
    fi
    
    # Verify new version
    NEW_VERSION=$($ATUIN_BIN --version 2>/dev/null | awk '{print $2}')
    if [ "$NEW_VERSION" = "$LATEST_VERSION" ]; then
        log_message "Successfully updated Atuin from $CURRENT_VERSION to $LATEST_VERSION"
        backup_cleanup $SERVICE_NAME
    else
        log_message "Version mismatch after update. Expected: $LATEST_VERSION, Got: $NEW_VERSION"
        log_message "Restoring from backup..."
        backup_restore $SERVICE_NAME "$ATUIN_BIN"
        exit 1
    fi
else
    log_message "Atuin is already at the latest version ($CURRENT_VERSION)"
fi

exit 0