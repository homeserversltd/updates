#!/bin/bash

# Mount NAS Service Update Hotfix
# This script updates the mountNas.service to the new configuration with vault dependencies
# Target: Systems with existing mountNas.service file

SCRIPT_NAME="mount_nas_service_update"
LOG_FILE="/var/log/homeserver/hotfix_mount_nas.log"

log_info()  { echo "[${SCRIPT_NAME}] INFO: $*" | tee -a "$LOG_FILE"; }
log_warn()  { echo "[${SCRIPT_NAME}] WARN: $*" | tee -a "$LOG_FILE" >&2; }
log_error() { echo "[${SCRIPT_NAME}] ERROR: $*" | tee -a "$LOG_FILE" >&2; }

# Check if we're running as root
if [ "$(id -u)" -ne 0 ]; then
    log_error "This script must be run as root"
    exit 1
fi

# Configuration
SERVICE_FILE="/etc/systemd/system/mountNas.service"
SERVICE_BACKUP="/etc/systemd/system/mountNas.service.backup.$(date +%s)"

# Desired service file content (hardcoded desired state)
DESIRED_CONTENT='[Unit]
Description=NAS Mount Status
ConditionPathExists=/vault/scripts/init.sh
ConditionPathIsMountPoint=/vault
Requires=vault.mount
After=vault.mount

[Service]
Type=oneshot
ExecStart=/vault/scripts/init.sh
StandardOutput=journal
StandardError=journal
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target'

# Check if service file exists
check_service_exists() {
    if [ -f "$SERVICE_FILE" ]; then
        log_info "Mount NAS service file found: $SERVICE_FILE"
        return 0
    else
        log_warn "Mount NAS service file not found: $SERVICE_FILE"
        return 1
    fi
}

# Check if service file matches desired state
check_service_matches() {
    if [ ! -f "$SERVICE_FILE" ]; then
        return 1
    fi
    
    # Compare current file with desired content
    if diff -q <(echo "$DESIRED_CONTENT") "$SERVICE_FILE" >/dev/null 2>&1; then
        log_info "Service file already matches desired state"
        return 0
    else
        log_info "Service file does not match desired state, update needed"
        return 1
    fi
}

# Create backup of existing service file
create_backup() {
    if [ -f "$SERVICE_FILE" ]; then
        log_info "Creating backup of existing service file: $SERVICE_BACKUP"
        if cp "$SERVICE_FILE" "$SERVICE_BACKUP"; then
            log_info "Backup created successfully"
            return 0
        else
            log_error "Failed to create backup"
            return 1
        fi
    else
        log_info "No existing service file to backup"
        return 0
    fi
}

# Update service file to desired state
update_service_file() {
    log_info "Updating mountNas.service to new configuration"
    
    # Write the desired content to the service file
    if echo "$DESIRED_CONTENT" > "$SERVICE_FILE"; then
        log_info "Service file updated successfully"
        return 0
    else
        log_error "Failed to update service file"
        return 1
    fi
}

# Verify the updated service file
verify_service_file() {
    log_info "Verifying updated service file"
    
    # Check if file exists
    if [ ! -f "$SERVICE_FILE" ]; then
        log_error "Service file does not exist after update"
        return 1
    fi
    
    # Check if content matches desired state
    if ! check_service_matches; then
        log_error "Service file does not match desired state after update"
        return 1
    fi
    
    # Check if file is valid systemd unit
    if systemd-analyze verify "$SERVICE_FILE" >/dev/null 2>&1; then
        log_info "Service file is valid systemd unit"
    else
        log_warn "Service file validation failed, but continuing"
    fi
    
    log_info "Service file verification passed"
    return 0
}

# Stop the service if it's running (since we're changing from restarting to oneshot)
stop_service() {
    log_info "Checking if Mount NAS service is running"
    
    if systemctl is-active --quiet mountNas.service 2>/dev/null; then
        log_info "Mount NAS service is running, stopping it"
        if systemctl stop mountNas.service; then
            log_info "Mount NAS service stopped successfully"
        else
            log_warn "Failed to stop Mount NAS service, but continuing with update"
        fi
    else
        log_info "Mount NAS service is not running"
    fi
    
    return 0
}

# Main execution
main() {
    log_info "Starting Mount NAS service update hotfix"
    
    # Check if service file exists
    if ! check_service_exists; then
        log_info "Mount NAS service file not found, creating new one"
    fi
    
    # Check if service already matches desired state
    if check_service_matches; then
        log_info "Service file already matches desired state, no update needed"
        exit 0
    fi
    
    # Stop the service if it's running
    stop_service
    
    # Create backup
    if ! create_backup; then
        log_error "Failed to create backup, aborting"
        exit 1
    fi
    
    # Update service file
    if ! update_service_file; then
        log_error "Failed to update service file"
        exit 1
    fi
    
    # Verify the update
    if ! verify_service_file; then
        log_error "Service file verification failed"
        exit 1
    fi
    
    # Note: Systemd reload and service restart handled separately
    
    log_info "Mount NAS service update hotfix completed successfully"
    log_info "Service file updated with vault dependencies and proper configuration"
}

# Run main function
main "$@"
