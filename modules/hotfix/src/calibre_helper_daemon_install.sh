#!/bin/bash

# Calibre Helper Daemon Installation Hotfix
# This script ensures the Calibre Helper Daemon is installed if Calibre Web exists
# Target: Systems with Calibre Web service installed

set -e

SCRIPT_NAME="calibre_helper_daemon_install"
LOG_FILE="/var/log/homeserver/hotfix_calibre_helper.log"

log_info()  { echo "[${SCRIPT_NAME}] INFO: $*" | tee -a "$LOG_FILE"; }
log_warn()  { echo "[${SCRIPT_NAME}] WARN: $*" | tee -a "$LOG_FILE" >&2; }
log_error() { echo "[${SCRIPT_NAME}] ERROR: $*" | tee -a "$LOG_FILE" >&2; }

# Check if we're running as root
if [ "$(id -u)" -ne 0 ]; then
    log_error "This script must be run as root"
    exit 1
fi

# Configuration
CALIBRE_WEB_SERVICE="/etc/systemd/system/calibre-web.service"
HELPER_DAEMON_SCRIPT="/usr/local/sbin/calibreHelperDaemon.sh"
HELPER_FEEDER_SERVICE="/etc/systemd/system/calibre-feeder.service"
HELPER_WATCHER_SERVICE="/etc/systemd/system/calibre-watch.service"

# Check if Calibre Web service exists
check_calibre_web_exists() {
    if [ -f "$CALIBRE_WEB_SERVICE" ]; then
        log_info "Calibre Web service found: $CALIBRE_WEB_SERVICE"
        return 0
    else
        log_info "Calibre Web service not found, skipping helper daemon installation"
        return 1
    fi
}

# Check if helper daemon script exists
check_helper_script_exists() {
    if [ -f "$HELPER_DAEMON_SCRIPT" ]; then
        log_info "Helper daemon script found: $HELPER_DAEMON_SCRIPT"
        return 0
    else
        log_warn "Helper daemon script not found: $HELPER_DAEMON_SCRIPT"
        return 1
    fi
}

# Check if helper daemon services are already installed
check_helper_services_installed() {
    local feeder_exists=false
    local watcher_exists=false
    
    if [ -f "$HELPER_FEEDER_SERVICE" ]; then
        feeder_exists=true
        log_info "Feeder service already installed: $HELPER_FEEDER_SERVICE"
    fi
    
    if [ -f "$HELPER_WATCHER_SERVICE" ]; then
        watcher_exists=true
        log_info "Watcher service already installed: $HELPER_WATCHER_SERVICE"
    fi
    
    if [ "$feeder_exists" = true ] && [ "$watcher_exists" = true ]; then
        log_info "Helper daemon services already installed"
        return 0
    else
        log_info "Helper daemon services not fully installed"
        return 1
    fi
}

# Install helper daemon
install_helper_daemon() {
    log_info "Installing Calibre Helper Daemon..."
    
    if [ ! -f "$HELPER_DAEMON_SCRIPT" ]; then
        log_error "Helper daemon script not found: $HELPER_DAEMON_SCRIPT"
        log_error "Cannot install helper daemon without the script"
        return 1
    fi
    
    # Make sure the script is executable
    chmod +x "$HELPER_DAEMON_SCRIPT"
    log_info "Made helper daemon script executable"
    
    # Run the installer
    if "$HELPER_DAEMON_SCRIPT" install system; then
        log_info "Helper daemon installed successfully"
        return 0
    else
        log_error "Failed to install helper daemon"
        return 1
    fi
}

# Verify installation
verify_installation() {
    log_info "Verifying helper daemon installation..."
    
    # Check if services exist
    if [ ! -f "$HELPER_FEEDER_SERVICE" ]; then
        log_error "Feeder service not found after installation"
        return 1
    fi
    
    if [ ! -f "$HELPER_WATCHER_SERVICE" ]; then
        log_error "Watcher service not found after installation"
        return 1
    fi
    
    # Check if services are enabled
    if systemctl is-enabled --quiet calibre-feeder.service 2>/dev/null; then
        log_info "Feeder service is enabled"
    else
        log_warn "Feeder service is not enabled"
    fi
    
    if systemctl is-enabled --quiet calibre-watch.service 2>/dev/null; then
        log_info "Watcher service is enabled"
    else
        log_warn "Watcher service is not enabled"
    fi
    
    # Check if services are running
    if systemctl is-active --quiet calibre-watch.service 2>/dev/null; then
        log_info "Watcher service is running"
    else
        log_info "Watcher service is not running (may be normal if no books to process)"
    fi
    
    log_info "Helper daemon installation verified"
    return 0
}

# Main execution
main() {
    log_info "Starting Calibre Helper Daemon installation hotfix"
    
    # Check if Calibre Web exists
    if ! check_calibre_web_exists; then
        log_info "Calibre Web not found, skipping helper daemon installation"
        exit 0
    fi
    
    # Check if helper daemon is already installed
    if check_helper_services_installed; then
        log_info "Helper daemon already installed, no action needed"
        exit 0
    fi
    
    # Check if helper script exists
    if ! check_helper_script_exists; then
        log_error "Cannot install helper daemon - script not found"
        log_error "Please ensure calibreHelperDaemon.sh is installed at $HELPER_DAEMON_SCRIPT"
        exit 1
    fi
    
    # Install helper daemon
    if ! install_helper_daemon; then
        log_error "Failed to install helper daemon"
        exit 1
    fi
    
    # Verify installation
    if ! verify_installation; then
        log_error "Helper daemon installation verification failed"
        exit 1
    fi
    
    log_info "Calibre Helper Daemon installation hotfix completed successfully"
    log_info "Helper daemon is now installed and ready to process books"
}

# Run main function
main "$@"
