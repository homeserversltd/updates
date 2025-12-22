#!/bin/bash

# HOMESERVER Update Manager
# Orchestrates the Python-based schema-driven update system
# Repository URL is configured in index.json metadata section

# Ensure PATH includes common system directories
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH"

# Paths
PYTHON_UPDATES_DIR="/usr/local/lib/updates"
PYTHON_ORCHESTRATOR="$PYTHON_UPDATES_DIR/index.py"
LOG_DIR="/var/log/homeserver"
LOG_FILE="$LOG_DIR/update.log"

# Function to log messages with timestamps
log_message() {
    # Try multiple date command locations for robustness
    if command -v date >/dev/null 2>&1; then
        timestamp="$(date '+%Y-%m-%d %H:%M:%S')"
    elif [ -x "/usr/bin/date" ]; then
        timestamp="$(/usr/bin/date '+%Y-%m-%d %H:%M:%S')"
    elif [ -x "/bin/date" ]; then
        timestamp="$(:; /bin/date '+%Y-%m-%d %H:%M:%S')"
    else
        timestamp="$(python3 -c "import datetime; print(datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))")"
    fi
    # Echo to stdout only; update runs may redirect this to the log file
    echo "[${timestamp}] [INFO] $1"
}

# Ensure the centralized update log exists before Python sets up handlers
ensure_log_file() {
    # Create directory if missing
    if [ ! -d "$LOG_DIR" ]; then
        mkdir -p "$LOG_DIR" 2>/dev/null || true
    
    fi
    # Touch the log file if missing
    if [ ! -f "$LOG_FILE" ]; then
        touch "$LOG_FILE" 2>/dev/null || true
        # Best-effort sane permissions
        chmod 664 "$LOG_FILE" 2>/dev/null || true
    fi

    # Do not truncate here; truncation happens only for actual update runs
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
            log_message "Executing: /usr/bin/python3 -m updates.index --check-only"
            cd /usr/local/lib && /usr/bin/python3 -m updates.index --check-only
            ;;
        "legacy")
            log_message "Running legacy manifest-based updates..."
            log_message "Executing: /usr/bin/python3 -m updates.index --legacy"
            cd /usr/local/lib && /usr/bin/python3 -m updates.index --legacy
            ;;
        "full"|*)
            log_message "Running schema-based updates..."
            log_message "Executing: /usr/bin/python3 -m updates.index"
            cd /usr/local/lib && /usr/bin/python3 -m updates.index
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

# Function to run module management operations
run_module_management() {
    local operation="$1"
    local target="$2"
    local component="$3"
    
    log_message "Running module management operation: $operation"
    
    case "$operation" in
        "enable")
            if [ -n "$component" ]; then
                log_message "Enabling component '$component' in module '$target'..."
                cd /usr/local/lib && /usr/bin/python3 -m updates.index --enable-component "$target" "$component"
            else
                log_message "Enabling module '$target'..."
                cd /usr/local/lib && /usr/bin/python3 -m updates.index --enable-module "$target"
            fi
            ;;
        "disable")
            if [ -n "$component" ]; then
                log_message "Disabling component '$component' in module '$target'..."
                cd /usr/local/lib && /usr/bin/python3 -m updates.index --disable-component "$target" "$component"
            else
                log_message "Disabling module '$target'..."
                cd /usr/local/lib && /usr/bin/python3 -m updates.index --disable-module "$target"
            fi
            ;;
        "list")
            log_message "Listing all modules..."
            cd /usr/local/lib && /usr/bin/python3 -m updates.index --list-modules
            ;;
        "status")
            if [ -n "$target" ]; then
                log_message "Getting status for module '$target'..."
                cd /usr/local/lib && /usr/bin/python3 -m updates.index --module-status "$target"
            else
                log_message "Getting status for all modules..."
                cd /usr/local/lib && /usr/bin/python3 -m updates.index --all-status
            fi
            ;;
    esac
    
    local exit_status=$?
    
    if [ $exit_status -eq 0 ]; then
        log_message "✓ Module management operation completed successfully"
    else
        log_message "✗ Module management operation failed with exit code $exit_status"
    fi
    
    return $exit_status
}

# Function to show usage
show_usage() {
    echo "HOMESERVER Update Manager"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Update Operations:"
    echo "  --check         Check for updates without applying them"
    echo "  --legacy        Use legacy manifest-based updates"
    echo "  --help          Show this help message"
    echo ""
    echo "Module Management:"
    echo "  --enable <module>                Enable a module"
    echo "  --disable <module>               Disable a module"
    echo "  --enable-component <module> <component>   Enable a specific component"
    echo "  --disable-component <module> <component>  Disable a specific component"
    echo "  --list-modules                   List all available modules"
    echo "  --status [module]                Show status (all modules or specific module)"
    echo ""
    echo "Examples:"
    echo "  $0 --enable website              # Enable website module"
    echo "  $0 --disable adblock             # Disable adblock module"
    echo "  $0 --enable-component website frontend   # Enable frontend component in website"
    echo "  $0 --status website              # Show website module status"
    echo "  $0 --list-modules                # List all modules with status"
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
    local operation=""
    local target=""
    local component=""
    
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
            --enable)
                operation="enable"
                target="$2"
                if [ -z "$target" ]; then
                    log_message "Error: --enable requires a module name"
                    show_usage
                    exit 1
                fi
                shift 2
                ;;
            --disable)
                operation="disable"
                target="$2"
                if [ -z "$target" ]; then
                    log_message "Error: --disable requires a module name"
                    show_usage
                    exit 1
                fi
                shift 2
                ;;
            --enable-component)
                operation="enable"
                target="$2"
                component="$3"
                if [ -z "$target" ] || [ -z "$component" ]; then
                    log_message "Error: --enable-component requires module and component names"
                    show_usage
                    exit 1
                fi
                shift 3
                ;;
            --disable-component)
                operation="disable"
                target="$2"
                component="$3"
                if [ -z "$target" ] || [ -z "$component" ]; then
                    log_message "Error: --disable-component requires module and component names"
                    show_usage
                    exit 1
                fi
                shift 3
                ;;
            --list-modules)
                operation="list"
                shift
                ;;
            --status)
                operation="status"
                target="$2"
                if [ -n "$target" ]; then
                    shift 2
                else
                    shift
                fi
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
    
    # If this is an actual update run (no module-management operation and not --check),
    # clear the log and redirect all output (stdout+stderr) to the log file.
    if [ -z "$operation" ] && [ "$mode" != "check" ]; then
        ensure_log_file
        : > "$LOG_FILE" 2>/dev/null || true
        export PYTHONUNBUFFERED=1
        exec > "$LOG_FILE" 2>&1
    fi

    log_message "Starting HOMESERVER update manager..."
    
    # Check if Python system is available
    if ! check_python_system; then
        log_message "Python update system not available"
        exit 1
    fi
    
    # Handle module management operations
    if [ -n "$operation" ]; then
        log_message "Operation: $operation"
        if [ -n "$target" ]; then
            log_message "Target: $target"
        fi
        if [ -n "$component" ]; then
            log_message "Component: $component"
        fi
        
        if run_module_management "$operation" "$target" "$component"; then
            log_message "Module management completed successfully"
            exit 0
        else
            log_message "Module management failed"
            exit 1
        fi
    fi
    
    # Handle update operations
    log_message "Mode: $mode"
    
    # Log execution context for debugging
    log_message "About to execute Python update orchestrator: $PYTHON_ORCHESTRATOR"
    log_message "Python command: /usr/bin/python3 -m updates.index"
    log_message "Working directory: /usr/local/lib"
    
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
