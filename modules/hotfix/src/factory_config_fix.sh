#!/bin/bash

# Factory Config Creation Hotfix
# This script ensures /etc/homeserver.factory exists as an immutable backup
# Target: All schema versions (universal hotfix)

set -e

SCRIPT_NAME="factory_config_fix"
LOG_FILE="/var/log/homeserver/hotfix_factory.log"

log_info()  { echo "[${SCRIPT_NAME}] INFO: $*" | tee -a "$LOG_FILE"; }
log_warn()  { echo "[${SCRIPT_NAME}] WARN: $*" | tee -a "$LOG_FILE" >&2; }
log_error() { echo "[${SCRIPT_NAME}] ERROR: $*" | tee -a "$LOG_FILE" >&2; }

# Check if we're running as root
if [ "$(id -u)" -ne 0 ]; then
    log_error "This script must be run as root"
    exit 1
fi

# Configuration
FACTORY_CONFIG="/etc/homeserver.factory"
SOURCE_CONFIGS=(
    "/var/www/homeserver/src/config/homeserver.json"
    "/var/www/homeserver/src/config/homeserver.factory"
    "/etc/homeserver.json"
)

# Find the best source config file
find_source_config() {
    log_info "Searching for source configuration file..."
    
    for config_path in "${SOURCE_CONFIGS[@]}"; do
        if [ -f "$config_path" ]; then
            log_info "Found source config: $config_path"
            echo "$config_path"
            return 0
        fi
    done
    
    log_error "No source configuration file found in any expected location"
    return 1
}

# Check if factory config already exists and is valid
check_factory_config() {
    if [ -f "$FACTORY_CONFIG" ]; then
        # Check if it's a valid JSON file
        if python3 -m json.tool "$FACTORY_CONFIG" >/dev/null 2>&1; then
            log_info "Factory config already exists and is valid: $FACTORY_CONFIG"
            return 0
        else
            log_warn "Factory config exists but is not valid JSON, will recreate"
            return 1
        fi
    else
        log_info "Factory config does not exist: $FACTORY_CONFIG"
        return 1
    fi
}

# Create the factory config from source
create_factory_config() {
    local source_config="$1"
    
    log_info "Creating factory config from: $source_config"
    
    # Copy the source config to factory location
    if cp "$source_config" "$FACTORY_CONFIG"; then
        log_info "Factory config copied successfully"
    else
        log_error "Failed to copy source config to factory location"
        return 1
    fi
    
    # Set proper ownership and permissions
    chown root:root "$FACTORY_CONFIG"
    chmod 444 "$FACTORY_CONFIG"
    log_info "Set ownership to root:root and permissions to 444"
    
    # Make the file immutable
    if chattr +i "$FACTORY_CONFIG" 2>/dev/null; then
        log_info "Made factory config immutable with chattr +i"
    else
        log_warn "Failed to make factory config immutable (chattr not available or insufficient privileges)"
    fi
    
    # Verify the file is readable and valid JSON
    if python3 -m json.tool "$FACTORY_CONFIG" >/dev/null 2>&1; then
        log_info "Factory config created and verified successfully"
        return 0
    else
        log_error "Factory config creation failed - file is not valid JSON"
        return 1
    fi
}

# Verify factory config is properly protected
verify_factory_config() {
    log_info "Verifying factory config protection..."
    
    # Check if file exists
    if [ ! -f "$FACTORY_CONFIG" ]; then
        log_error "Factory config file does not exist after creation"
        return 1
    fi
    
    # Check ownership
    local owner=$(stat -c '%U:%G' "$FACTORY_CONFIG")
    if [ "$owner" != "root:root" ]; then
        log_warn "Factory config ownership is $owner, expected root:root"
    else
        log_info "Factory config ownership is correct: $owner"
    fi
    
    # Check permissions
    local perms=$(stat -c '%a' "$FACTORY_CONFIG")
    if [ "$perms" != "444" ]; then
        log_warn "Factory config permissions are $perms, expected 444"
    else
        log_info "Factory config permissions are correct: $perms"
    fi
    
    # Check if immutable flag is set (if chattr is available)
    if command -v lsattr >/dev/null 2>&1; then
        local attrs=$(lsattr "$FACTORY_CONFIG" 2>/dev/null | cut -d' ' -f1)
        if [[ "$attrs" == *"i"* ]]; then
            log_info "Factory config is immutable (chattr +i)"
        else
            log_warn "Factory config is not immutable"
        fi
    else
        log_info "Cannot check immutable flag (lsattr not available)"
    fi
    
    # Verify JSON validity
    if python3 -m json.tool "$FACTORY_CONFIG" >/dev/null 2>&1; then
        log_info "Factory config contains valid JSON"
        return 0
    else
        log_error "Factory config does not contain valid JSON"
        return 1
    fi
}

# Main execution
main() {
    log_info "Starting factory config creation hotfix"
    
    # Check if factory config already exists and is valid
    if check_factory_config; then
        log_info "Factory config already exists and is valid, no action needed"
        exit 0
    fi
    
    # Find source config
    local source_config
    if ! source_config=$(find_source_config); then
        log_error "Cannot proceed without source configuration"
        exit 1
    fi
    
    # Create factory config
    if ! create_factory_config "$source_config"; then
        log_error "Failed to create factory config"
        exit 1
    fi
    
    # Verify the result
    if ! verify_factory_config; then
        log_error "Factory config verification failed"
        exit 1
    fi
    
    log_info "Factory config creation hotfix completed successfully"
    log_info "Factory config is now available at: $FACTORY_CONFIG"
}

# Run main function
main "$@"
