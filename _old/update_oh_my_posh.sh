#!/bin/bash
set -e

# Source utilities
source "$(dirname "$0")/config/utils.sh"

# Configuration
SERVICE_NAME="oh-my-posh"
OH_MY_POSH_BIN="/usr/local/bin/oh-my-posh"

# Check mode - only verify service
if [ "$1" = "--check" ]; then
    if [ -f "$OH_MY_POSH_BIN" ] && [ -x "$OH_MY_POSH_BIN" ]; then
        VERSION=$($OH_MY_POSH_BIN --version 2>/dev/null | grep -oE '[0-9.]+')
        if [ -n "$VERSION" ]; then
            log_message "OK - Current version: $VERSION"
            exit 0
        fi
    fi
    log_message "oh-my-posh binary not found at $OH_MY_POSH_BIN"
    exit 1
fi

# Get the current installed version
CURRENT_VERSION=$($OH_MY_POSH_BIN --version 2>/dev/null | grep -oE '[0-9.]+')
if [[ -z "$CURRENT_VERSION" ]]; then
    log_message "Failed to get current version of oh-my-posh"
    exit 1
fi
log_message "Current oh-my-posh version: $CURRENT_VERSION"

# Get the latest version from the official source
LATEST_VERSION=$(curl -s https://api.github.com/repos/JanDeDobbeleer/oh-my-posh/releases/latest | grep -oP '"tag_name": "\K(.*)(?=")')
if [[ -z "$LATEST_VERSION" ]]; then
    log_message "Failed to get latest version information"
    exit 1
fi

# Remove the 'v' prefix if it exists
LATEST_VERSION=${LATEST_VERSION#v}
log_message "Latest available version: $LATEST_VERSION"

# Compare versions
if [[ "$CURRENT_VERSION" != "$LATEST_VERSION" ]]; then
    log_message "Update available. Creating backup..."
    backup_create $SERVICE_NAME "$OH_MY_POSH_BIN" ".bin"
    
    log_message "Installing update..."
    if ! curl -s https://ohmyposh.dev/install.sh | bash -s -- -d $INSTALL_DIR; then
        log_message "Update failed, restoring from backup..."
        backup_restore $SERVICE_NAME "$OH_MY_POSH_BIN"
        exit 1
    fi
    
    # Verify new version
    NEW_VERSION=$($OH_MY_POSH_BIN --version 2>/dev/null | grep -oE '[0-9.]+')
    if [[ "$NEW_VERSION" == "$LATEST_VERSION" ]]; then
        log_message "Successfully updated oh-my-posh to version $NEW_VERSION"
        backup_cleanup $SERVICE_NAME
    else
        log_message "Version mismatch after update. Expected: $LATEST_VERSION, Got: $NEW_VERSION"
        log_message "Restoring from backup..."
        backup_restore $SERVICE_NAME "$OH_MY_POSH_BIN"
        exit 1
    fi
else
    log_message "oh-my-posh is already at the latest version"
fi

exit 0
