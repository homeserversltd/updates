#!/bin/bash

# Migration 00000002: Ensure Factory Config Exists
# 
# This migration ensures /etc/homeserver.factory exists as an immutable backup
# of the homeserver configuration. This is foundational infrastructure needed
# by all HOMESERVER installations.
#
# Idempotent: Safe to run multiple times
# Universal: Applies to all systems regardless of version

set +e  # Do not exit on error - we handle errors explicitly

echo "========================================"
echo "Migration 00000002: Factory Config Creation"
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
FACTORY_CONFIG="/etc/homeserver.factory"
SOURCE_CONFIGS=(
    "/var/www/homeserver/src/config/homeserver.json"
    "/var/www/homeserver/src/config/homeserver.factory"
    "/etc/homeserver.json"
)

# IDEMPOTENCY CHECK: Does factory config already exist and is it valid?
log "Checking if factory config already exists..."
if [ -f "$FACTORY_CONFIG" ]; then
    if python3 -m json.tool "$FACTORY_CONFIG" >/dev/null 2>&1; then
        log "SUCCESS: Factory config already exists and is valid: $FACTORY_CONFIG"
        log "Migration already applied, exiting successfully"
        exit 0
    else
        log "WARNING: Factory config exists but is not valid JSON, will recreate"
    fi
else
    log "Factory config does not exist: $FACTORY_CONFIG"
fi

# Find the best source config file
log "Searching for source configuration file..."
SOURCE_CONFIG=""
for config_path in "${SOURCE_CONFIGS[@]}"; do
    if [ -f "$config_path" ]; then
        log "Found source config: $config_path"
        SOURCE_CONFIG="$config_path"
        break
    fi
done

if [ -z "$SOURCE_CONFIG" ]; then
    log "ERROR: No source configuration file found in any expected location"
    exit 1
fi

# Create factory config from source
log "Creating factory config from: $SOURCE_CONFIG"

# Remove old factory config if it exists but is invalid
if [ -f "$FACTORY_CONFIG" ]; then
    log "Removing existing invalid factory config"
    chattr -i "$FACTORY_CONFIG" 2>/dev/null || true
    rm -f "$FACTORY_CONFIG"
fi

# Copy the source config to factory location
if ! cp "$SOURCE_CONFIG" "$FACTORY_CONFIG"; then
    log "ERROR: Failed to copy source config to factory location"
    exit 1
fi
log "Factory config copied successfully"

# Set proper ownership and permissions
chown root:root "$FACTORY_CONFIG"
chmod 444 "$FACTORY_CONFIG"
log "Set ownership to root:root and permissions to 444 (read-only)"

# Make the file immutable
if chattr +i "$FACTORY_CONFIG" 2>/dev/null; then
    log "Made factory config immutable with chattr +i"
else
    log "WARNING: Could not make factory config immutable (chattr not available)"
fi

# Verify the file is readable and valid JSON
if ! python3 -m json.tool "$FACTORY_CONFIG" >/dev/null 2>&1; then
    log "ERROR: Factory config is not valid JSON after creation"
    exit 1
fi

log "Factory config created and verified successfully"

# Verify protection settings
log "Verifying factory config protection..."

# Check ownership
OWNER=$(stat -c '%U:%G' "$FACTORY_CONFIG")
if [ "$OWNER" != "root:root" ]; then
    log "WARNING: Factory config ownership is $OWNER, expected root:root"
else
    log "Factory config ownership is correct: $OWNER"
fi

# Check permissions
PERMS=$(stat -c '%a' "$FACTORY_CONFIG")
if [ "$PERMS" != "444" ]; then
    log "WARNING: Factory config permissions are $PERMS, expected 444"
else
    log "Factory config permissions are correct: $PERMS"
fi

# Check immutable flag if available
if command -v lsattr >/dev/null 2>&1; then
    ATTRS=$(lsattr "$FACTORY_CONFIG" 2>/dev/null | cut -d' ' -f1)
    if [[ "$ATTRS" == *"i"* ]]; then
        log "Factory config is immutable (chattr +i)"
    else
        log "WARNING: Factory config is not immutable"
    fi
fi

# Success
log ""
log "========================================"
log "SUCCESS: Migration completed"
log "========================================"
log ""
log "Factory config is now available at: $FACTORY_CONFIG"
log "The file is read-only and serves as an immutable backup"
log ""

exit 0

