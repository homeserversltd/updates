#!/bin/bash

# HOMESERVER Update Manager
# Orchestrates the Python-based schema-driven update system

# Paths
PYTHON_UPDATES_DIR="/usr/local/lib/updates"
PYTHON_ORCHESTRATOR="$PYTHON_UPDATES_DIR/index.py"

# Function to log messages with timestamps
log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Function to check if Python system is available
check_python_system() {
    if [ -f "$PYTHON_ORCHESTRATOR" ]; then
        return 0
    else
        log_message "Error: Python orchestrator not found at $PYTHON_ORCHESTRATOR"
        return 1
    fi
}

# Function to run the Python-based update system
run_python_updates() {
    local mode="$1"
    
    log_message "Using Python-based update system"
    log_message "Orchestrator: $PYTHON_ORCHESTRATOR"
    
    case "$mode" in
        "check")
            log_message "Running update check (no changes will be made)..."
            python3 "$PYTHON_ORCHESTRATOR" --check-only
            ;;
        "legacy")
            log_message "Running legacy manifest-based updates..."
            python3 "$PYTHON_ORCHESTRATOR" --legacy
            ;;
        "full"|*)
            log_message "Running schema-based updates..."
            python3 "$PYTHON_ORCHESTRATOR"
            ;;
    esac
    
    local exit_status=$?
    
    if [ $exit_status -eq 0 ]; then
        log_message "✓ Update system completed successfully"
    else
        log_message "✗ Update system failed with exit code $exit_status"
    fi
    
    return $exit_status
}

# Function to show usage
show_usage() {
    echo "HOMESERVER Update Manager"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --check         Check for updates without applying them"
    echo "  --legacy        Use legacy manifest-based updates"
    echo "  --help          Show this help message"
    echo ""
    echo "Default behavior:"
    echo "  Run schema-based updates (Git sync + module updates)"
    echo ""
    echo "Update System:"
    echo "  Python:  $PYTHON_ORCHESTRATOR"
    echo "  Modules: $PYTHON_UPDATES_DIR/modules/"
}

main() {
    local mode="full"
    
    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --check)
                mode="check"
                shift
                ;;
            --legacy)
                mode="legacy"
                shift
                ;;
            --help|-h)
                show_usage
                exit 0
                ;;
            *)
                log_message "Unknown option: $1"
                show_usage
                exit 1
                ;;
        esac
    done
    
    log_message "Starting HOMESERVER update manager..."
    log_message "Mode: $mode"
    
    # Check if Python system is available
    if ! check_python_system; then
        log_message "Python update system not available"
        exit 1
    fi
    
    # Run the Python update system
    if run_python_updates "$mode"; then
        log_message "Update manager completed successfully"
        exit 0
    else
        log_message "Update manager failed"
        exit 1
    fi
}

# Run the main function with all arguments
main "$@"
