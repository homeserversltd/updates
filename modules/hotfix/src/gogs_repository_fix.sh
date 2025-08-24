#!/bin/bash

# Gogs Repository Path Fix Hotfix
# This script fixes Gogs to use local storage instead of NAS dependency
# Target schema version: 0.1.7 and below

set -e

SCRIPT_NAME="gogs_repository_fix"
LOG_FILE="/var/log/homeserver/hotfix_gogs.log"

log_info()  { echo "[${SCRIPT_NAME}] INFO: $*" | tee -a "$LOG_FILE"; }
log_warn()  { echo "[${SCRIPT_NAME}] WARN: $*" | tee -a "$LOG_FILE" >&2; }
log_error() { echo "[${SCRIPT_NAME}] ERROR: $*" | tee -a "$LOG_FILE" >&2; }

# Check if we're running as root
if [ "$(id -u)" -ne 0 ]; then
    log_error "This script must be run as root"
    exit 1
fi

# Fix the repository path in app.ini (only the specific line)
fix_repository_path() {
    local app_ini="/opt/gogs/custom/conf/app.ini"
    
    if [ ! -f "$app_ini" ]; then
        log_error "Gogs app.ini not found: $app_ini"
        return 1
    fi
    
    # Check if the path is already correct
    if grep -q "ROOT = /opt/gogs/repositories" "$app_ini"; then
        log_info "Repository path is already correct, no changes needed"
        return 0
    fi
    
    log_info "Fixing repository path in app.ini"
    
    # Backup the original file
    cp "$app_ini" "${app_ini}.backup.$(date +%s)"
    
    # Replace only the ROOT line, preserving everything else
    sed -i 's|^ROOT = .*|ROOT = /opt/gogs/repositories|' "$app_ini"
    
    # Verify the change
    if grep -q "ROOT = /opt/gogs/repositories" "$app_ini"; then
        log_info "Repository path updated successfully"
        return 0
    else
        log_error "Failed to update repository path"
        return 1
    fi
}

# Create local repository directory with proper permissions
create_local_directories() {
    log_info "Checking local repository directories"
    
    # Check if directory already exists with correct permissions
    if [ -d "/opt/gogs/repositories" ]; then
        local owner=$(stat -c '%U:%G' "/opt/gogs/repositories")
        local perms=$(stat -c '%a' "/opt/gogs/repositories")
        
        if [ "$owner" = "git:git" ] && [ "$perms" = "750" ]; then
            log_info "Local repository directories already exist with correct permissions"
            return 0
        else
            log_info "Directory exists but permissions need fixing"
        fi
    else
        log_info "Creating local repository directories"
    fi
    
    # Create the repositories directory
    mkdir -p /opt/gogs/repositories
    chown -R git:git /opt/gogs/repositories
    chmod 750 /opt/gogs/repositories
    
    log_info "Local repository directories created/updated with proper permissions"
}

# Update the systemd service file to remove NAS dependency
fix_service_file() {
    local service_file="/etc/systemd/system/gogs.service"
    
    if [ ! -f "$service_file" ]; then
        log_error "Gogs service file not found: $service_file"
        return 1
    fi
    
    # Check if ReadWritePaths line already exists
    if ! grep -q "ReadWritePaths=" "$service_file"; then
        log_info "Service file already correct (no ReadWritePaths), no changes needed"
        return 0
    fi
    
    log_info "Updating systemd service file to remove ReadWritePaths"
    
    # Backup the original file
    cp "$service_file" "${service_file}.backup.$(date +%s)"
    
    # Remove the ReadWritePaths line if it exists
    sed -i '/ReadWritePaths=/d' "$service_file"
    
    log_info "Service file updated successfully"
}

# Check if admin user exists and create if needed
check_and_create_admin_user() {
    log_info "Checking for Gogs admin user"
    
    # Check if the gogs service is running
    if ! systemctl is-active --quiet gogs.service; then
        log_warn "Gogs service is not running, cannot check for admin user"
        return 0
    fi
    
    # Check if admin user exists by querying the database
    local admin_exists=$(su - postgres -c "psql -d gogs -t -c \"SELECT COUNT(*) FROM \\\"user\\\" WHERE name = 'owner' AND is_admin = true;\" 2>/dev/null" | tr -d ' ')
    
    if [ "$admin_exists" = "1" ]; then
        log_info "Admin user 'owner' already exists"
        return 0
    else
        log_info "Admin user 'owner' not found, creating..."
        
        # Read the skeleton key for password
        local password_file="/root/key/skeleton.key"
        if [ ! -f "$password_file" ]; then
            log_error "Skeleton key file not found: $password_file"
            return 1
        fi
        
        local password=$(cat "$password_file")
        
        # Create the admin user
        if su - git -c "/opt/gogs/gogs admin create-user --name=owner --password='$password' --email=owner@home.arpa --admin=true"; then
            log_info "Admin user 'owner' created successfully"
            return 0
        else
            log_error "Failed to create admin user"
            return 1
        fi
    fi
}

# Reload systemd and restart Gogs
restart_service() {
    log_info "Checking if Gogs service needs restart"
    
    # Check if service is running and healthy
    if systemctl is-active --quiet gogs.service; then
        # Check if the service is using the correct config
        local current_root=$(grep "ROOT = " /opt/gogs/custom/conf/app.ini | cut -d'=' -f2 | tr -d ' ')
        if [ "$current_root" = "/opt/gogs/repositories" ]; then
            log_info "Gogs service is running with correct configuration, no restart needed"
            return 0
        else
            log_info "Configuration changed, service restart required"
        fi
    else
        log_info "Service is not running, starting required"
    fi
    
    log_info "Reloading systemd and restarting Gogs service"
    
    systemctl daemon-reload
    
    if systemctl restart gogs.service; then
        log_info "Gogs service restarted successfully"
        
        # Wait a moment for the service to stabilize
        sleep 5
        
        if systemctl is-active --quiet gogs.service; then
            log_info "Gogs service is running and healthy"
            return 0
        else
            log_error "Gogs service failed to start properly"
            return 1
        fi
    else
        log_error "Failed to restart Gogs service"
        return 1
    fi
}

# Main execution
main() {
    log_info "Starting Gogs repository path fix hotfix"
    
    # Apply all fixes
    local success=true
    
    if ! fix_repository_path; then
        log_error "Failed to fix repository path"
        success=false
    fi
    
    if ! create_local_directories; then
        log_error "Failed to create local directories"
        success=false
    fi
    
    if ! fix_service_file; then
        log_error "Failed to fix service file"
        success=false
    fi
    
    if ! restart_service; then
        log_error "Failed to restart service"
        success=false
    fi
    
    # Try to create admin user (don't fail the hotfix if this fails)
    if ! check_and_create_admin_user; then
        log_warn "Admin user creation failed, but hotfix will continue"
    fi
    
    if [ "$success" = true ]; then
        log_info "Gogs repository path fix hotfix completed successfully"
        exit 0
    else
        log_error "Gogs repository path fix hotfix failed"
        exit 1
    fi
}

# Run main function
main "$@"
