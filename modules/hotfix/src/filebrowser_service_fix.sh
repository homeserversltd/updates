#!/bin/bash

# Filebrowser Service Fix Hotfix
# This script removes NAS dependency from filebrowser.service
# Target: Systems with existing filebrowser.service that has NAS dependency

SCRIPT_NAME="filebrowser_service_fix"
LOG_FILE="/var/log/homeserver/hotfix_filebrowser.log"

log_info()  { echo "[${SCRIPT_NAME}] INFO: $*" | tee -a "$LOG_FILE"; }
log_warn()  { echo "[${SCRIPT_NAME}] WARN: $*" | tee -a "$LOG_FILE" >&2; }
log_error() { echo "[${SCRIPT_NAME}] ERROR: $*" | tee -a "$LOG_FILE" >&2; }

# Check if we're running as root
if [ "$(id -u)" -ne 0 ]; then
    log_error "This script must be run as root"
    exit 1
fi

# Configuration
SERVICE_FILE="/etc/systemd/system/filebrowser.service"
SERVICE_BACKUP="/etc/systemd/system/filebrowser.service.backup.$(date +%s)"

# Desired service file content (without NAS dependency)
DESIRED_CONTENT='[Unit]
Description=File Browser
After=network.target 

[Service]
Type=simple
User=filebrowser
Group=filebrowser
ExecStart=/usr/local/bin/filebrowser -d /etc/filebrowser/filebrowser.db
WorkingDirectory=/etc/filebrowser
Restart=on-failure
RestartSec=5
StartLimitInterval=60s
StartLimitBurst=3

[Install]
WantedBy=multi-user.target'

# Check if service file exists
check_service_exists() {
    if [ -f "$SERVICE_FILE" ]; then
        log_info "Filebrowser service file found: $SERVICE_FILE"
        return 0
    else
        log_warn "Filebrowser service file not found: $SERVICE_FILE"
        return 1
    fi
}

# Check if service file has NAS dependency
check_has_nas_dependency() {
    if [ ! -f "$SERVICE_FILE" ]; then
        return 1
    fi
    
    # Check for NAS-related ExecStartPre line
    if grep -q "ExecStartPre=.*test.*mnt/nas" "$SERVICE_FILE"; then
        log_info "Service file has NAS dependency (ExecStartPre line found)"
        return 0
    else
        log_info "Service file does not have NAS dependency"
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

# Update service file to remove NAS dependency
update_service_file() {
    log_info "Updating filebrowser.service to remove NAS dependency"
    
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
    
    # Verify NAS dependency was removed
    if grep -q "ExecStartPre=.*test.*mnt/nas" "$SERVICE_FILE"; then
        log_error "NAS dependency still present in service file"
        return 1
    else
        log_info "NAS dependency successfully removed"
    fi
    
    log_info "Service file verification passed"
    return 0
}

# Reload systemd and restart service
reload_and_restart() {
    log_info "Reloading systemd daemon"
    
    if systemctl daemon-reload; then
        log_info "Systemd daemon reloaded successfully"
    else
        log_error "Failed to reload systemd daemon"
        return 1
    fi
    
    log_info "Restarting filebrowser service"
    
    if systemctl restart filebrowser.service; then
        log_info "Filebrowser service restarted successfully"
        
        # Wait a moment for the service to stabilize
        sleep 3
        
        if systemctl is-active --quiet filebrowser.service; then
            log_info "Filebrowser service is running and healthy"
            return 0
        else
            log_error "Filebrowser service failed to start properly"
            return 1
        fi
    else
        log_error "Failed to restart filebrowser service"
        return 1
    fi
}

# Main execution
main() {
    log_info "Starting Filebrowser service fix hotfix"
    
    # Check if service file exists
    if ! check_service_exists; then
        log_info "Filebrowser service file not found, creating new one"
    fi
    
    # Check if service already matches desired state
    if check_service_matches; then
        log_info "Service file already matches desired state, no update needed"
        exit 0
    fi
    
    # Check if service has NAS dependency (our target condition)
    if ! check_has_nas_dependency; then
        log_info "Service file does not have NAS dependency, but updating to ensure correct configuration"
    fi
    
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
    
    # Reload systemd and restart service
    if ! reload_and_restart; then
        log_error "Failed to reload systemd or restart service"
        exit 1
    fi
    
    log_info "Filebrowser service fix hotfix completed successfully"
    log_info "NAS dependency removed from filebrowser.service"
}

# Run main function
main "$@"
