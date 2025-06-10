# Updates Orchestrator System

## Overview

This directory implements a **schema-version driven** Python update orchestration system for managing and updating services and components. The system enables live, dynamic management of service updates by comparing schema versions between local modules and a GitHub repository source of truth.

## Architecture

The update system follows a Git-based approach:

1. **Git Repository Sync**: Clone/pull from a GitHub repository containing the latest module definitions
2. **Schema Version Comparison**: Compare `schema_version` in each module's `index.json` (local vs repository)
3. **Atomic Module Updates**: Completely replace local module directories when repository has newer schema version
4. **Module Execution**: Run each module's update scripts which handle their own configuration changes
5. **Global Index Tracking**: Maintain a global index tracking current versions of all modules

Each module is self-contained and version-independent, enabling safe atomic updates with automatic rollback on failure.

## Key Features

- **Schema-Version Driven**: Updates based on semantic versioning in module `index.json` files
- **Git Repository Integration**: Automatic sync from remote GitHub repository
- **Atomic Updates**: Complete module directory replacement ensures consistency
- **Automatic Backup & Rollback**: Failed updates automatically restore from backup
- **Global Version Tracking**: Central `index.json` tracks current module versions
- **Dual Mode Support**: Both new schema-based and legacy manifest-based updates
- **Robust Error Handling**: Individual module failures don't halt the entire process
- **Shell Script Integration**: Convenient `updateManager.sh` wrapper for common operations

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
- `utils/` - Shared utilities for logging, version comparison, and Git operations

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
        "description": "Network-level ad blocking service"
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

### Example Module index.py

```python
def main(args=None):
    """
    Main entry point for module update.
    
    Args:
        args: Optional command line arguments
    """
    print("Updating adblock module...")
    
    # Module-specific update logic
    # - Update configuration files
    # - Restart services
    # - Verify functionality
    
    print("Adblock module update completed")
```

## How Schema Updates Work

1. **Repository Sync**: Git clone/pull latest module definitions from repository
2. **Version Detection**: Compare each module's `schema_version` between local and repository
3. **Update Selection**: Identify modules where repository version > local version
4. **Backup Creation**: Create `.backup` copy of existing module directory
5. **Atomic Replacement**: Copy entire module directory from repository to local
6. **Module Execution**: Run the module's `main()` function to apply changes
7. **Index Update**: Update global `index.json` with new version numbers
8. **Rollback on Failure**: Restore from backup if any step fails

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

The `__init__.py` module provides utility functions for module development:

- `load_module_index(path)` - Load module index.json
- `compare_schema_versions(v1, v2)` - Compare semantic versions
- `sync_from_repo(url, path, branch)` - Git sync operations
- `detect_module_updates(local, repo)` - Find modules needing updates
- `update_modules(modules, local, repo)` - Execute module updates
- `run_update(module_path, args)` - Run individual module
- `run_updates_async(updates)` - Parallel module execution

## Legacy Support

The system maintains backward compatibility with the previous manifest-driven approach:

```bash
# Run legacy updates
python3 index.py --legacy
```

This fallback ensures existing manifest-based modules continue to function during the transition period.

## Best Practices

- **Idempotent Updates**: Modules should be safe to run multiple times
- **Self-Contained Logic**: Each module handles its own dependencies and configuration
- **Proper Error Handling**: Use try/catch blocks and meaningful error messages
- **Schema Versioning**: Increment schema version for any breaking changes
- **Configuration Validation**: Verify configuration files and service states
- **Atomic Operations**: Group related changes to enable clean rollback

## Dependencies

The system uses only Python standard library modules:
- `json` - Configuration file parsing
- `subprocess` - Git operations and system commands
- `shutil` - File and directory operations
- `pathlib` - Path manipulation
- `asyncio` - Asynchronous execution support
- `concurrent.futures` - Parallel module execution

No external dependencies are required, ensuring system reliability.

## Security Considerations

- **Git Repository Trust**: Only sync from trusted repository sources
- **File System Permissions**: Module directories require appropriate write permissions
- **Backup Integrity**: Verify backup creation before proceeding with updates
- **Atomic Operations**: Use temporary directories for staging before final deployment
- **Error Isolation**: Module failures contained to prevent system-wide issues

## Monitoring and Logging

All operations are logged with timestamps and appropriate log levels:

```
[2024-12-08 10:30:15] Starting schema-based update orchestration
[2024-12-08 10:30:16] Repository: https://github.com/homeserverltd/updates.git
[2024-12-08 10:30:17] Module adblock needs update: 1.0.0 → 1.1.0
[2024-12-08 10:30:18] Updated module adblock
[2024-12-08 10:30:19] Update orchestration completed: 1 successful, 0 failed
```

Log output can be redirected or parsed for monitoring system integration.

## License

This system is intended for internal HOMESERVER use. Adapt and extend as needed for your environment.