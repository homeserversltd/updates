#!/bin/bash
set -e

# Source utilities
source "$(dirname "$0")/config/utils.sh"

# Configuration
SERVICE_NAME="vaultwarden"
DATA_DIR="/var/lib/vaultwarden"
CONFIG_FILE="/etc/vaultwarden.env"
VAULTWARDEN_BIN="/opt/vaultwarden/vaultwarden"
WEB_VAULT_DIR="/opt/vaultwarden/web-vault"
LOG_DIR="/var/log/vaultwarden"
ATTACHMENTS_DIR="/mnt/nas/vaultwarden/attachments"

# Check mode - only verify service
if [ "$1" = "--check" ]; then
    VAULTWARDEN_BIN="/opt/vaultwarden/vaultwarden"
    CARGO_TOML="/opt/vaultwarden/src/Cargo.toml"
    WEB_VERSION_JSON="/opt/vaultwarden/web-vault/version.json"
    
    # First check if binary exists and is executable
    if [ ! -f "$VAULTWARDEN_BIN" ] || [ ! -x "$VAULTWARDEN_BIN" ]; then
        log_message "Vaultwarden not found at $VAULTWARDEN_BIN or not executable"
        exit 1
    fi
    
    # Method 1: Try --version flag
    VERSION=$($VAULTWARDEN_BIN --version 2>&1 | grep -oP '\d+\.\d+\.\d+' || echo "")
    
    # Method 2: Try Cargo.toml if version flag failed
    if [ -z "$VERSION" ] && [ -f "$CARGO_TOML" ]; then
        VERSION=$(grep -Po '^version = "\K[^"]*' "$CARGO_TOML" || echo "")
    fi
    
    # Method 3: Try web-vault version.json if still no version
    if [ -z "$VERSION" ] && [ -f "$WEB_VERSION_JSON" ]; then
        VERSION=$(cat "$WEB_VERSION_JSON" | grep -Po '"version":.*"\K[^"]*' || echo "")
    fi
    
    # If we found a version through any method, report success
    if [ -n "$VERSION" ]; then
        log_message "OK - Current version: $VERSION"
        exit 0
    fi
    
    # If all methods failed, report error but with more detail
    log_message "Vaultwarden is installed but version could not be determined"
    exit 1
fi

# Get current version
CURRENT_VERSION=$($VAULTWARDEN_BIN --version 2>&1 | head -n1 | cut -d' ' -f2)
if [ -z "$CURRENT_VERSION" ]; then
    log_message "Failed to get current version of Vaultwarden"
    exit 1
fi
log_message "Current Vaultwarden version: $CURRENT_VERSION"

# Get latest version from GitHub
LATEST_VERSION=$(curl -s https://api.github.com/repos/dani-garcia/vaultwarden/releases/latest | grep -oP '"tag_name": "\K(.*)(?=")')
if [ -z "$LATEST_VERSION" ]; then
    log_message "Failed to get latest version information"
    exit 1
fi

log_message "Latest available version: $LATEST_VERSION"

if [ "$CURRENT_VERSION" = "$LATEST_VERSION" ]; then
    log_message "Vaultwarden is already at the latest version"
    exit 0
fi

# Stop service
log_message "Stopping Vaultwarden service..."
systemctl stop $SERVICE_NAME

# Create backup
log_message "Creating backup..."
backup_create $SERVICE_NAME "$DATA_DIR"
backup_create $SERVICE_NAME "$CONFIG_FILE" ".env"
backup_create $SERVICE_NAME "$VAULTWARDEN_BIN" ".bin"
backup_create $SERVICE_NAME "$WEB_VAULT_DIR" "_web.tar.gz"
backup_create $SERVICE_NAME "$LOG_DIR" "_logs.tar.gz"
backup_create $SERVICE_NAME "$ATTACHMENTS_DIR" "_attachments.tar.gz"

# Cleanup old backups
log_message "Cleaning up old backups..."
backup_cleanup $SERVICE_NAME

# Update Vaultwarden
log_message "Installing new version..."
if ! CARGO_HOME=/usr/local/cargo PATH=/usr/local/cargo/bin:$PATH cargo install vaultwarden --features postgresql; then
    log_message "Failed to build/install vaultwarden"
    backup_restore $SERVICE_NAME "$DATA_DIR"
    backup_restore $SERVICE_NAME "$CONFIG_FILE"
    backup_restore $SERVICE_NAME "$VAULTWARDEN_BIN"
    backup_restore $SERVICE_NAME "$WEB_VAULT_DIR"
    backup_restore $SERVICE_NAME "$LOG_DIR"
    backup_restore $SERVICE_NAME "$ATTACHMENTS_DIR"
    systemctl start $SERVICE_NAME
    exit 1
fi

# Copy binary to system location
if ! cp ~/.cargo/bin/vaultwarden "$VAULTWARDEN_BIN"; then
    log_message "Failed to copy binary to system location"
    backup_restore $SERVICE_NAME "$DATA_DIR"
    backup_restore $SERVICE_NAME "$CONFIG_FILE"
    backup_restore $SERVICE_NAME "$VAULTWARDEN_BIN"
    backup_restore $SERVICE_NAME "$WEB_VAULT_DIR"
    backup_restore $SERVICE_NAME "$LOG_DIR"
    backup_restore $SERVICE_NAME "$ATTACHMENTS_DIR"
    systemctl start $SERVICE_NAME
    exit 1
fi

chmod +x "$VAULTWARDEN_BIN"
chown vaultwarden:vaultwarden "$VAULTWARDEN_BIN"

# Update web vault
log_message "Updating web vault..."
LATEST_WEB_VERSION=$(curl -s https://api.github.com/repos/dani-garcia/bw_web_builds/releases/latest | grep -oP '"tag_name": "\K(.*)(?=")')
if [ -z "$LATEST_WEB_VERSION" ]; then
    log_message "Failed to get latest web vault version"
    backup_restore $SERVICE_NAME "$DATA_DIR"
    backup_restore $SERVICE_NAME "$CONFIG_FILE"
    backup_restore $SERVICE_NAME "$VAULTWARDEN_BIN"
    backup_restore $SERVICE_NAME "$WEB_VAULT_DIR"
    backup_restore $SERVICE_NAME "$LOG_DIR"
    backup_restore $SERVICE_NAME "$ATTACHMENTS_DIR"
    systemctl start $SERVICE_NAME
    exit 1
fi

# Download and install web vault
rm -rf "$WEB_VAULT_DIR"
mkdir -p "$WEB_VAULT_DIR"
if ! curl -L "https://github.com/dani-garcia/bw_web_builds/releases/download/${LATEST_WEB_VERSION}/bw_web_${LATEST_WEB_VERSION}.tar.gz" \
     -o "/tmp/web_vault.tar.gz"; then
    log_message "Failed to download web vault"
    backup_restore $SERVICE_NAME "$WEB_VAULT_DIR"
    systemctl start $SERVICE_NAME
    exit 1
fi

if ! tar xf "/tmp/web_vault.tar.gz" -C "$WEB_VAULT_DIR" --strip-components=1; then
    log_message "Failed to extract web vault"
    rm -f "/tmp/web_vault.tar.gz"
    backup_restore $SERVICE_NAME "$WEB_VAULT_DIR"
    systemctl start $SERVICE_NAME
    exit 1
fi

rm -f "/tmp/web_vault.tar.gz"
chown -R vaultwarden:vaultwarden "$WEB_VAULT_DIR"

# Start service
log_message "Starting Vaultwarden service..."
systemctl start $SERVICE_NAME

# Wait for service to start
sleep 5

# Check service status
if ! systemctl is-active --quiet $SERVICE_NAME; then
    log_message "Service failed to start, restoring from backup..."
    backup_restore $SERVICE_NAME "$DATA_DIR"
    backup_restore $SERVICE_NAME "$CONFIG_FILE"
    backup_restore $SERVICE_NAME "$VAULTWARDEN_BIN"
    backup_restore $SERVICE_NAME "$WEB_VAULT_DIR"
    backup_restore $SERVICE_NAME "$LOG_DIR"
    backup_restore $SERVICE_NAME "$ATTACHMENTS_DIR"
    systemctl start $SERVICE_NAME
    exit 1
fi

log_message "Update completed successfully!"
log_message "New version: $($VAULTWARDEN_BIN --version 2>&1 | head -n1)"
systemctl status $SERVICE_NAME
exit 0