#!/bin/bash
#
# Gogs Emergency Recovery Script
# 
# This script restores Gogs from backup when the update module nukes the installation.
# Based on real-world recovery experience from catastrophic update failure.
#
# Usage: ./gogs_recovery.sh [--dry-run] [--backup-path PATH]
#
# The update module treats Gogs as a simple binary replacement, completely
# overwriting /opt/gogs without preserving repositories or custom configuration.
# This script restores the complete installation from the backup created by
# the update module's state manager.

set -o errexit
set -o nounset
set -o pipefail

# Configuration
DEFAULT_BACKUP_BASE="/var/backups/updates"
GOGS_INSTALL_DIR="/opt/gogs"
GOGS_SERVICE="gogs"
GOGS_USER="git"
GOGS_GROUP="git"

# Colors for output (avoiding colored text per user preference)
LOG_PREFIX="[GOGS-RECOVERY]"

# Parse command line arguments
DRY_RUN=false
BACKUP_PATH=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --backup-path)
            BACKUP_PATH="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [--dry-run] [--backup-path PATH]"
            echo "  --dry-run     Show what would be done without making changes"
            echo "  --backup-path Custom backup path (default: auto-detect)"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Logging function
log() {
    echo "${LOG_PREFIX} $1"
}

log_error() {
    echo "${LOG_PREFIX} ERROR: $1" >&2
}

# Find the most recent Gogs backup
find_gogs_backup() {
    local search_path="${BACKUP_PATH:-${DEFAULT_BACKUP_BASE}}"
    
    log "Searching for Gogs backup in: ${search_path}"
    
    # Look for gogs_backup directories
    local backup_dirs=($(find "${search_path}" -name "*gogs*backup*" -type d 2>/dev/null | sort -r))
    
    if [[ ${#backup_dirs[@]} -eq 0 ]]; then
        log_error "No Gogs backup found in ${search_path}"
        return 1
    fi
    
    # Find the most recent backup with the expected structure
    for backup_dir in "${backup_dirs[@]}"; do
        local gogs_backup_path="${backup_dir}/files/opt/gogs"
        if [[ -d "${gogs_backup_path}" ]]; then
            log "Found Gogs backup: ${gogs_backup_path}"
            echo "${gogs_backup_path}"
            return 0
        fi
    done
    
    log_error "No valid Gogs backup structure found"
    return 1
}

# Verify backup contains critical data
verify_backup() {
    local backup_path="$1"
    
    log "Verifying backup integrity..."
    
    # Check for critical directories
    local critical_dirs=("repositories" "custom" "data")
    for dir in "${critical_dirs[@]}"; do
        if [[ ! -d "${backup_path}/${dir}" ]]; then
            log_error "Backup missing critical directory: ${dir}"
            return 1
        fi
    done
    
    # Check for Gogs binary
    if [[ ! -f "${backup_path}/gogs" ]]; then
        log_error "Backup missing Gogs binary"
        return 1
    fi
    
    # Check if repositories directory has content
    if [[ -z "$(ls -A "${backup_path}/repositories" 2>/dev/null)" ]]; then
        log "WARNING: Repositories directory is empty - no repos to restore"
    else
        log "Found repositories in backup"
    fi
    
    log "Backup verification passed"
    return 0
}

# Stop Gogs service
stop_gogs_service() {
    log "Stopping Gogs service..."
    
    if systemctl is-active --quiet "${GOGS_SERVICE}"; then
        if [[ "${DRY_RUN}" == "true" ]]; then
            log "DRY RUN: Would stop ${GOGS_SERVICE} service"
        else
            systemctl stop "${GOGS_SERVICE}"
            log "Gogs service stopped"
        fi
    else
        log "Gogs service already stopped"
    fi
}

# Restore from backup
restore_from_backup() {
    local backup_path="$1"
    
    log "Restoring Gogs from backup..."
    
    # Create target directory if it doesn't exist
    if [[ ! -d "${GOGS_INSTALL_DIR}" ]]; then
        if [[ "${DRY_RUN}" == "true" ]]; then
            log "DRY RUN: Would create directory ${GOGS_INSTALL_DIR}"
        else
            mkdir -p "${GOGS_INSTALL_DIR}"
            log "Created directory: ${GOGS_INSTALL_DIR}"
        fi
    fi
    
    # Copy all files from backup
    if [[ "${DRY_RUN}" == "true" ]]; then
        log "DRY RUN: Would copy ${backup_path}/* to ${GOGS_INSTALL_DIR}/"
    else
        cp -r "${backup_path}"/* "${GOGS_INSTALL_DIR}/"
        log "Files copied from backup"
    fi
}

# Fix ownership and permissions
fix_ownership() {
    log "Fixing ownership and permissions..."
    
    if [[ "${DRY_RUN}" == "true" ]]; then
        log "DRY RUN: Would set ownership to ${GOGS_USER}:${GOGS_GROUP}"
    else
        chown -R "${GOGS_USER}:${GOGS_GROUP}" "${GOGS_INSTALL_DIR}"
        log "Ownership set to ${GOGS_USER}:${GOGS_GROUP}"
    fi
}

# Start Gogs service
start_gogs_service() {
    log "Starting Gogs service..."
    
    if [[ "${DRY_RUN}" == "true" ]]; then
        log "DRY RUN: Would start ${GOGS_SERVICE} service"
    else
        systemctl start "${GOGS_SERVICE}"
        
        # Wait a moment for service to start
        sleep 3
        
        if systemctl is-active --quiet "${GOGS_SERVICE}"; then
            log "Gogs service started successfully"
        else
            log_error "Failed to start Gogs service"
            return 1
        fi
    fi
}

# Verify recovery
verify_recovery() {
    log "Verifying recovery..."
    
    if [[ "${DRY_RUN}" == "true" ]]; then
        log "DRY RUN: Would verify service status and repository access"
        return 0
    fi
    
    # Check service status
    if ! systemctl is-active --quiet "${GOGS_SERVICE}"; then
        log_error "Gogs service is not running"
        return 1
    fi
    
    # Check if repositories directory exists and has content
    if [[ -d "${GOGS_INSTALL_DIR}/repositories" ]]; then
        local repo_count=$(find "${GOGS_INSTALL_DIR}/repositories" -type d -mindepth 1 -maxdepth 1 | wc -l)
        log "Found ${repo_count} repositories restored"
    else
        log_error "Repositories directory missing after recovery"
        return 1
    fi
    
    # Check if custom config exists
    if [[ -f "${GOGS_INSTALL_DIR}/custom/conf/app.ini" ]]; then
        log "Custom configuration restored"
    else
        log_error "Custom configuration missing after recovery"
        return 1
    fi
    
    log "Recovery verification passed"
    return 0
}

# Main recovery function
main() {
    log "Starting Gogs emergency recovery..."
    
    # Find backup
    local backup_path
    if ! backup_path=$(find_gogs_backup); then
        log_error "Cannot proceed without backup"
        exit 1
    fi
    
    # Verify backup
    if ! verify_backup "${backup_path}"; then
        log_error "Backup verification failed"
        exit 1
    fi
    
    # Perform recovery steps
    stop_gogs_service
    restore_from_backup "${backup_path}"
    fix_ownership
    start_gogs_service
    
    # Verify recovery
    if ! verify_recovery; then
        log_error "Recovery verification failed"
        exit 1
    fi
    
    log "Gogs recovery completed successfully!"
    log "Access Gogs at: https://git.home.arpa/"
}

# Run main function
main "$@"
