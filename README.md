# Updates Orchestrator System

## Overview

This directory implements a **schema-version driven** Python update orchestration system for managing and updating services and components. The system enables live, dynamic management of service updates by comparing schema versions between local modules and a GitHub repository source of truth.

## Architecture

The update system follows a two-phase Git-based approach:

### Phase 1: Schema Updates (Infrastructure Maintenance)
1. **Git Repository Sync**: Clone/pull from a GitHub repository containing the latest module definitions
2. **Schema Version Comparison**: Compare `schema_version` in each module's `index.json` (local vs repository)
3. **Atomic Module Updates**: Completely replace local module directories when repository has newer schema version
4. **Self-Updating Orchestrator**: The system can update its own orchestrator code when repository contains newer versions

### Phase 2: Module Execution (Service Management)
5. **Enabled Module Detection**: Identify all modules marked as enabled in their `index.json`
6. **Universal Module Execution**: Run ALL enabled modules (regardless of whether they were schema-updated)
7. **Service Configuration**: Each module handles its own configuration changes, service restarts, and validation
8. **Global Index Tracking**: Maintain a global index tracking current versions of all modules

This two-phase approach ensures that:
- **Infrastructure stays current** through schema-based updates when code changes
- **All services remain properly configured** through universal execution of enabled modules
- **Each module is self-contained** and version-independent, enabling safe atomic updates with automatic rollback on failure

## Key Features

- **Schema-Version Driven**: Updates based on semantic versioning in module `index.json` files
- **Git Repository Integration**: Automatic sync from remote GitHub repository
- **Atomic Updates**: Complete module directory replacement ensures consistency
- **Automatic Backup & Rollback**: Failed updates automatically restore from backup
- **Global Version Tracking**: Central `index.json` tracks current module versions
- **Dual Mode Support**: Both new schema-based and legacy manifest-based updates
- **Robust Error Handling**: Individual module failures don't halt the entire process
- **Shell Script Integration**: Convenient `updateManager.sh` wrapper for common operations
- **Self-Updating Capability**: The orchestrator can update itself when newer versions are available

## System Paths

- **Local Modules**: `/var/local/lib/updates/modules/`
- **Global Index**: `/var/local/lib/updates/index.json`
- **Repository URL**: `https://github.com/homeserverltd/updates.git`
- **Temp Sync Path**: `/tmp/homeserver-updates-repo`

## Running Updates

### Using the Shell Manager (Recommended)

```bash
# Run schema-based updates (default)
/var/local/lib/updates/updateManager.sh

# Check for available updates without applying
/var/local/lib/updates/updateManager.sh --check

# Run legacy manifest-based updates
/var/local/lib/updates/updateManager.sh --legacy

# Show help
/var/local/lib/updates/updateManager.sh --help
```

### Direct Python Execution

```bash
# Schema-based updates
python3 /var/local/lib/updates/index.py

# Check-only mode
python3 /var/local/lib/updates/index.py --check-only

# Legacy mode
python3 /var/local/lib/updates/index.py --legacy

# Custom repository
python3 /var/local/lib/updates/index.py --repo-url https://github.com/custom/updates.git --branch develop
```

## Directory Structure

- `index.py` - Main orchestrator script implementing schema-based updates
- `__init__.py` - Package initialization with utility functions for module management
- `index.json` - Global index tracking current module versions and system metadata
- `updateManager.sh` - Shell wrapper providing convenient access to update functions
- `modules/` - Directory containing individual update modules
- `utils/` - Shared utilities for logging, version comparison, Git operations, and permissions
  - `permissions.py` - Centralized permission management system for all modules
  - `state_manager.py` - Backup and restore functionality for module states
  - `index.py` - Utility functions for module operations and logging

## Global Index Format

The `index.json` file tracks the current state of all modules:

```json
{
    "metadata": {
        "schema_version": "1.0.0",
        "channel": "stable"
    },
    "packages": {
        "adblock": "1.0.0",
        "atuin": "1.0.0",
        "filebrowser": "1.0.0",
        "gogs": "1.0.0",
        "ohmyposh": "1.0.0",
        "os": "1.0.0",
        "vaultwarden": "1.0.0",
        "venvs": "1.0.0",
        "website": "1.0.0",
        "hotfix": "1.0.0"
    }
}
```

## Module Structure

Each module directory must contain:

- `index.json` - Module metadata with schema version
- `index.py` - Main module script with `main(args)` function
- Optional: `__init__.py`, `README.md`, configuration files

### Example Module index.json

```json
{
    "metadata": {
        "schema_version": "1.2.0",
        "name": "adblock",
        "description": "Network-level ad blocking service",
        "enabled": true
    },
    "configuration": {
        "service_name": "adblock",
        "config_path": "/etc/adblock/config.json",
        "backup_paths": [
            "/etc/adblock/",
            "/var/lib/adblock/"
        ]
    }
}
```

**Important**: The `enabled` field in metadata determines whether a module will be executed during the universal execution phase. Modules default to `enabled: true` if not specified.

### Example Module index.py

```python
from updates.utils.permissions import PermissionManager, PermissionTarget
from updates.utils.state_manager import StateManager
from updates.index import log_message

def restore_service_permissions():
    """Restore proper permissions after update."""
    try:
        permission_manager = PermissionManager("service_name")
        
        # Build targets from module configuration
        targets = [
            PermissionTarget(
                path="/opt/service",
                owner="service_user",
                group="service_group",
                mode=0o755,
                recursive=True
            ),
            PermissionTarget(
                path="/var/lib/service",
                owner="service_user", 
                group="service_group",
                mode=0o755,
                recursive=True
            )
        ]
        
        return permission_manager.set_permissions(targets)
    except Exception as e:
        log_message(f"Permission restoration failed: {e}", "ERROR")
        return False

def main(args=None):
    """
    Main entry point for module execution.
    
    This function is called during the universal execution phase for all enabled modules.
    It should be idempotent and handle both initial setup and ongoing maintenance.
    
    Args:
        args: Optional command line arguments
    """
    log_message("Executing service module...")
    
    try:
        # Module-specific execution logic (runs every update cycle)
        # - Verify configuration files are current
        # - Ensure services are running with correct settings
        # - Update any dynamic configurations
        # - Restart services if needed
        # - Validate functionality
        
        # Always restore permissions after any changes
        if not restore_service_permissions():
            log_message("Warning: Permission restoration failed", "WARNING")
        
        log_message("Service module execution completed")
        return {"success": True}
        
    except Exception as e:
        log_message(f"Module execution failed: {e}", "ERROR")
        return {"success": False, "error": str(e)}
```

**Note**: The `main()` function runs during every update cycle for enabled modules, not just when the module code is updated. Design your modules to be idempotent and handle both initial setup and ongoing maintenance. **Always restore permissions** after making changes to prevent service failures.

## How the Two-Phase Update Process Works

### Phase 1: Schema-Based Infrastructure Updates

1. **Repository Sync**: Git clone/pull latest module definitions from repository
2. **Orchestrator Check**: Determine if the orchestrator system itself needs updating
3. **Module Version Detection**: Compare each module's `schema_version` between local and repository
4. **Update Selection**: Identify modules where repository version > local version
5. **Backup Creation**: Create `.backup` copy of existing module directory
6. **Atomic Replacement**: Copy entire module directory from repository to local
7. **Orchestrator Update**: If needed, update orchestrator system files after modules are updated

### Phase 2: Universal Module Execution

8. **Enabled Module Discovery**: Scan all modules and identify those marked as `enabled: true`
9. **Universal Execution**: Run ALL enabled modules' `main()` functions (not just updated ones)
10. **Service Management**: Each module handles its own configuration, service restarts, and validation
11. **Index Update**: Update global `index.json` with new version numbers
12. **Rollback on Failure**: Restore from backup if any step fails

### Key Differences from Single-Phase Systems

- **Schema updates** only happen when code/infrastructure changes (version mismatches)
- **Module execution** happens for ALL enabled modules on every update cycle
- **Services stay configured** even when no schema updates are needed
- **Infrastructure stays current** through selective schema-based updates

## Self-Updating Orchestrator

The system can update its own core files when the repository contains a newer version:

1. **Schema Version Check**: Compare orchestrator schema version in local vs repository `index.json`
2. **Backup Creation**: Create backup of orchestrator files before updating
3. **Core File Update**: Update orchestrator files including:
   - `index.py` - Main orchestrator script
   - `updateManager.sh` - Shell wrapper
   - `__init__.py` - Package utilities
   - `utils/` - Shared utilities
   - Additional configuration files
4. **Restart Awareness**: System is aware when it has updated itself and needs restarting
5. **Rollback Protection**: Automatic rollback if orchestrator update fails

## Version Comparison

The system uses semantic versioning comparison:

- `1.0.0` < `1.0.1` (patch update)
- `1.0.1` < `1.1.0` (minor update)  
- `1.1.0` < `2.0.0` (major update)

Updates are only applied when the repository has a higher schema version than the local module.

## Error Handling and Rollback

- **Individual Module Failures**: Other modules continue updating if one fails
- **Automatic Backup**: Each module backed up before update
- **Rollback on Failure**: Failed modules automatically restored from backup
- **Detailed Logging**: All operations logged with timestamps and error details
- **Exit Codes**: Non-zero exit codes indicate failures for script integration

## Adding New Modules

1. **Create Module Directory**: Add new directory under `modules/`
2. **Add index.json**: Define schema version and metadata
3. **Add index.py**: Implement `main(args)` function
4. **Repository Integration**: Commit module to Git repository
5. **Automatic Detection**: System will detect and apply on next update run

No changes to the orchestrator are required - new modules are automatically discovered.

## Command Line Options

### index.py Options

```bash
--repo-url URL          Git repository URL (default: homeserverltd/updates.git)
--local-repo PATH       Local sync path (default: /tmp/homeserver-updates-repo)
--modules-path PATH     Local modules directory (default: /var/local/lib/updates)
--branch BRANCH         Git branch to sync (default: main)
--legacy                Use legacy manifest-based updates
--check-only            Check for updates without applying
```

### updateManager.sh Options

```bash
--check                 Check for updates without applying
--legacy                Use legacy manifest-based updates  
--help                  Show usage information
```

## Utility Functions

The update system provides several utility modules for module development:

### Core Utilities (`__init__.py`)
- `load_module_index(path)` - Load module index.json
- `compare_schema_versions(v1, v2)` - Compare semantic versions
- `sync_from_repo(url, path, branch)` - Git sync operations
- `detect_module_updates(local, repo)` - Find modules needing updates
- `update_modules(modules, local, repo)` - Execute module updates
- `run_update(module_path, args)` - Run individual module
- `run_updates_async(updates)` - Parallel module execution

### Permission Management (`utils/permissions.py`)
- `PermissionManager(module_name)` - Main permission management class
- `PermissionTarget(path, owner, group, mode, ...)` - Permission target definition
- `restore_service_permissions_simple(...)` - Simple service permission restoration
- `create_service_permission_targets(...)` - Create standard permission targets
- `fix_common_service_permissions(service_name)` - Fix permissions for common locations

### State Management (`utils/state_manager.py`)
- `StateManager()` - Backup and restore functionality for module states
- `backup_module_state(module_name, description, files)` - Create module backups
- `restore_module_state(module_name)` - Restore from backup

### Example Usage
```python
from updates.utils.permissions import PermissionManager, PermissionTarget
from updates.utils.state_manager import StateManager
from updates.index import log_message

# Permission management
permission_manager = PermissionManager("my_service")
success = permission_manager.set_permissions([
    PermissionTarget("/opt/service", "service", "service", 0o755, recursive=True)
])

# State management
state_manager = StateManager()
backup_success = state_manager.backup_module_state("my_service", "pre_update", ["/opt/service"])
```

## Update Process Flow

### Phase 1: Schema Updates
1. **Initialization**: Parse command line arguments and set configuration
2. **Repository Sync**: Clone/pull from Git repository
3. **Orchestrator Check**: Determine if orchestrator needs updating
4. **Module Detection**: Find modules with newer schema versions in repository
5. **Schema Updates**: Update modules that have newer versions available
6. **Orchestrator Update**: If needed, update orchestrator system itself

### Phase 2: Module Execution
7. **Enabled Module Discovery**: Scan for all modules marked as enabled
8. **Universal Execution**: Run ALL enabled modules (regardless of schema updates)
9. **Service Management**: Each module configures services, restarts processes, validates functionality
10. **Global Index Update**: Update index.json with current module versions
11. **Summary**: Log summary of both schema updates and module executions

### Execution Logic
- **Always runs enabled modules**: Even if no schema updates are needed, all enabled modules execute
- **Schema updates are selective**: Only modules with version mismatches get their code updated
- **Service management is universal**: All enabled services get configured/validated on every run

## Legacy Support

The system maintains backward compatibility with the previous manifest-driven approach:

```bash
# Run legacy updates
python3 index.py --legacy
```

This fallback ensures existing manifest-based modules continue to function during the transition period.

## Best Practices

### Module Design
- **Idempotent Execution**: Modules must be safe to run multiple times (they execute every update cycle)
- **Self-Contained Logic**: Each module handles its own dependencies and configuration
- **Proper Error Handling**: Use try/catch blocks and meaningful error messages
- **State Validation**: Always verify current state before making changes
- **Service Management**: Handle service restarts gracefully and verify functionality
- **Permission Management**: Always restore proper permissions after making changes
- **Centralized Permissions**: Use PermissionManager instead of manual chmod/chown commands
- **Configuration-Driven**: Define permissions in index.json for consistency

### Schema Management
- **Schema Versioning**: Increment schema version only for code/infrastructure changes
- **Enabled Flag**: Use `enabled: false` to disable modules without removing them
- **Configuration Validation**: Verify configuration files and service states
- **Atomic Operations**: Group related changes to enable clean rollback

### Execution Patterns
- **Universal Execution**: Design modules knowing they run every cycle, not just on updates
- **Conditional Logic**: Check current state before applying changes
- **Resource Management**: Handle file locks, service states, and dependencies properly

## Dependencies

The system uses only Python standard library modules:
- `json` - Configuration file parsing
- `subprocess` - Git operations and system commands
- `shutil` - File and directory operations
- `pathlib` - Path manipulation
- `asyncio` - Asynchronous execution support
- `concurrent.futures` - Parallel module execution

No external dependencies are required, ensuring system reliability.

## Permission Management

The update system includes a centralized permission management system via `utils/permissions.py` that handles file ownership and permissions across all modules.

### PermissionManager Usage

Each module can use the `PermissionManager` class to restore proper permissions after updates:

```python
from updates.utils.permissions import PermissionManager, PermissionTarget

# Create permission manager for your module
permission_manager = PermissionManager("gogs")

# Define permission targets
targets = [
    PermissionTarget(
        path="/opt/gogs",
        owner="git",
        group="git", 
        mode=0o755,
        recursive=True
    ),
    PermissionTarget(
        path="/opt/gogs/gogs",
        owner="root",
        group="root",
        mode=0o755,
        target_type="file"
    )
]

# Apply permissions
success = permission_manager.set_permissions(targets)
```

### Module Configuration Integration

Modules can define permissions directly in their `index.json`:

```json
{
    "config": {
        "directories": {
            "install_dir": {
                "path": "/opt/gogs",
                "owner": "root",
                "mode": "755"
            },
            "data_dir": {
                "path": "/var/lib/gogs",
                "mode": "755"
            },
            "gogs_bin": {
                "path": "/opt/gogs/gogs",
                "owner": "root",
                "mode": "755"
            }
        },
        "permissions": {
            "owner": "git",
            "group": "git"
        }
    }
}
```

### Convenience Functions

The permission system provides helper functions for common patterns:

```python
from updates.utils.permissions import restore_service_permissions_simple

# Simple service permission restoration
success = restore_service_permissions_simple(
    service_name="gogs",
    config_dir="/etc/gogs",
    data_dir="/var/lib/gogs",
    binary_path="/opt/gogs/gogs"
)
```

### Permission Restoration Pattern

All modules should restore permissions after updates to prevent service failures:

```python
def restore_service_permissions():
    """Restore proper permissions after update."""
    try:
        permission_manager = PermissionManager("service_name")
        
        # Build targets from module configuration
        targets = []
        for dir_key, dir_config in config["directories"].items():
            targets.append(PermissionTarget(
                path=dir_config["path"],
                owner=dir_config.get("owner", default_owner),
                group=default_group,
                mode=int(dir_config["mode"], 8),
                recursive=os.path.isdir(path)
            ))
        
        return permission_manager.set_permissions(targets)
    except Exception as e:
        log_message(f"Permission restoration failed: {e}", "ERROR")
        return False
```

## Security Considerations

- **Git Repository Trust**: Only sync from trusted repository sources
- **File System Permissions**: Centralized permission management ensures consistent security
- **Permission Restoration**: All modules must restore proper permissions after updates
- **Backup Integrity**: Verify backup creation before proceeding with updates
- **Atomic Operations**: Use temporary directories for staging before final deployment
- **Error Isolation**: Module failures contained to prevent system-wide issues

## Monitoring and Logging

All operations are logged with timestamps and appropriate log levels:

```
[2024-12-08 10:30:15] Starting schema-based update orchestration
[2024-12-08 10:30:16] Repository: https://github.com/homeserverltd/updates.git
[2024-12-08 10:30:17] Schema updates needed: 1 modules, orchestrator: False
[2024-12-08 10:30:18] Module adblock needs update: 1.0.0 → 1.1.0
[2024-12-08 10:30:19] Updated module adblock
[2024-12-08 10:30:20] Getting enabled modules...
[2024-12-08 10:30:21] Found enabled module: adblock
[2024-12-08 10:30:21] Found enabled module: vaultwarden
[2024-12-08 10:30:21] Total enabled modules: 2
[2024-12-08 10:30:22] Running 2 enabled modules...
[2024-12-08 10:30:23] Executing module: adblock
[2024-12-08 10:30:24] ✓ Module 'adblock' executed successfully
[2024-12-08 10:30:25] Executing module: vaultwarden
[2024-12-08 10:30:26] ✓ Module 'vaultwarden' executed successfully
[2024-12-08 10:30:27] Module execution completed: 2 successful, 0 failed
[2024-12-08 10:30:28] Update orchestration completed:
[2024-12-08 10:30:28]   - Schema updates detected: 1
[2024-12-08 10:30:28]   - Successfully schema updated: 1
[2024-12-08 10:30:28]   - Enabled modules found: 2
[2024-12-08 10:30:28]   - Successfully executed: 2
```

Log output can be redirected or parsed for monitoring system integration. The two-phase logging clearly distinguishes between schema updates and module executions.
