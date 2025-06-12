# Updates System Utilities

## Overview

This directory contains utility modules that support the schema-driven updates orchestration system. The utilities provide shared functionality for logging, version control, and simple backup/restore operations that can be used across all update modules.

## Key Components

### Core Utilities (`__init__.py`)
Provides easy imports for commonly used utilities:
```python
from .index import log_message
from .version_control import checkout_module_version, list_module_versions
```

### Logging Utility (`index.py`)
Simple, consistent logging functionality for all update modules.

### Version Control (`version_control.py`) 
Git-based version control system for module management using Git tags and manifest tracking.

### State Manager (`state_manager.py`)
Simple single-backup-per-module state management system providing file, service, and database backup/restore capabilities.

## 📋 Logging Utility (`index.py`)

### log_message()
```python
from initialization.files.user_local_lib.updates.utils import log_message

log_message("Update started", "INFO")
log_message("Configuration updated successfully")  # Defaults to INFO
log_message("Failed to update service", "ERROR")
log_message("Service might need restart", "WARNING")
```

**Parameters:**
- `message` (str): The message to log
- `level` (str): Log level - "INFO" (default), "ERROR", "WARNING"

**Output Format:**
```
[2024-12-08 10:30:15] [INFO] Update started
[2024-12-08 10:30:16] [ERROR] Failed to update service
```

## 🔄 Version Control System (`version_control.py`)

Git-based version control system that uses tags and manifest version tracking.

### checkout_module_version()
```python
from initialization.files.user_local_lib.updates.utils.version_control import checkout_module_version

# Checkout to lastSafeVersion from manifest
success = checkout_module_version("adblock")

# Checkout to specific version
success = checkout_module_version("adblock", target_version="1.0.0")
```

**Parameters:**
- `module_name` (str): Name of the module to checkout
- `target_version` (str, optional): Specific version to checkout to

**Returns:** `bool` - True if successful

### list_module_versions()
```python
from initialization.files.user_local_lib.updates.utils.version_control import list_module_versions

versions = list_module_versions("adblock")
for version in versions:
    print(f"Version: {version['version']}")
    print(f"Tag: {version['tag']}")
    print(f"Timestamp: {version['timestamp']}")
```

**Returns:** List of dicts with version information:
```python
[
    {
        'tag': 'adblock-v1.0.0-20240610',
        'version': '1.0.0', 
        'timestamp': '20240610'
    }
]
```

### checkout_last_safe()
```python
from initialization.files.user_local_lib.updates.utils.version_control import checkout_last_safe

# Convenience function - checkout to lastSafeVersion
success = checkout_last_safe("adblock")
```

**Git Tag Convention:**
```
<module_name>-v<version>-<timestamp>
# Examples:
adblock-v1.0.0-20240610
gogs-v2.1.3-20241208
```

## 🛡️ State Manager (`state_manager.py`)

Simple single-backup-per-module state management system for update operations.

### Key Features
- **Single backup per module**: Each module gets exactly one backup slot
- **Automatic backup clobbering**: New backups replace previous ones
- **File, service, and database support**: Comprehensive state capture
- **Simple restore by module name**: No complex backup IDs
- **Predictable backup locations**: Consistent backup directory structure

### Basic Usage

#### StateManager Class
```python
from initialization.files.user_local_lib.updates.utils.state_manager import StateManager

# Create state manager instance
state_manager = StateManager("/var/backups/updates")

# Backup module state (clobbers any existing backup for this module)
state_manager.backup_module_state(
    module_name="mymodule",
    description="Pre-update backup",
    files=["/etc/mymodule/config.conf", "/opt/mymodule/"],
    services=["mymodule", "mymodule-worker"],
    databases=[{
        "type": "postgresql",
        "host": "localhost",
        "user": "mymodule",
        "database": "mymodule_db"
    }]
)

# Restore module state
success = state_manager.restore_module_state("mymodule")
```

#### File Operations
```python
# Backup files only
state_manager.backup_module_state(
    module_name="website",
    files=[
        "/var/www/homeserver/src",
        "/var/www/homeserver/backend",
        "/var/www/homeserver/package.json"
    ]
)

# Restore files
success = state_manager.restore_module_state("website")
```

#### Service Operations
```python
# Backup service states (enabled/disabled, active/inactive)
state_manager.backup_module_state(
    module_name="myservice",
    services=["nginx", "postgresql", "myservice"]
)

# Restore service states
success = state_manager.restore_module_state("myservice")
```

#### Database Operations
```python
# PostgreSQL backup
state_manager.backup_module_state(
    module_name="myapp",
    databases=[{
        "type": "postgresql",
        "host": "localhost",
        "port": "5432", 
        "user": "myapp",
        "password": "mypass",  # Optional
        "database": "myapp_db"
    }]
)

# SQLite backup
state_manager.backup_module_state(
    module_name="myapp",
    databases=[{
        "type": "sqlite",
        "database": "/var/lib/myapp/data.db"
    }]
)

# Restore database
success = state_manager.restore_module_state("myapp")
```

### Comprehensive Module Backup

Create complete module state backup:

```python
# Backup everything for a module
state_manager.backup_module_state(
    module_name="myservice",
    description="Complete pre-update backup",
    files=[
        "/etc/myservice/config.conf",
        "/opt/myservice/",
        "/var/lib/myservice/data/"
    ],
    services=["myservice", "myservice-worker"],
    databases=[{
        "type": "postgresql",
        "host": "localhost",
        "user": "myservice", 
        "database": "myservice_db"
    }]
)

# Perform update operations...
try:
    update_configuration()
    migrate_database() 
    restart_services()
except Exception as e:
    # Restore entire module state
    success = state_manager.restore_module_state("myservice")
```

### Backup Management

#### Check if Backup Exists
```python
# Check if module has a backup
has_backup = state_manager.has_backup("mymodule")

if has_backup:
    print("Backup exists for mymodule")
else:
    print("No backup found for mymodule")
```

#### Get Backup Information
```python
# Get backup details
backup_info = state_manager.get_backup_info("mymodule")

if backup_info:
    print(f"Module: {backup_info.module_name}")
    print(f"Created: {time.ctime(backup_info.timestamp)}")
    print(f"Description: {backup_info.description}")
    print(f"Files: {len(backup_info.files)}")
    print(f"Services: {len(backup_info.services)}")
    print(f"Databases: {len(backup_info.databases)}")
```

#### List All Module Backups
```python
# List all module backups
all_backups = state_manager.list_module_backups()

for module_name, backup_info in all_backups.items():
    print(f"Module: {module_name}")
    print(f"  Created: {time.ctime(backup_info.timestamp)}")
    print(f"  Description: {backup_info.description}")
```

#### Remove Module Backup
```python
# Remove backup for specific module
success = state_manager.remove_module_backup("mymodule")

if success:
    print("Backup removed successfully")
else:
    print("Failed to remove backup or backup not found")
```

### Data Classes

#### ModuleBackupInfo
```python
@dataclass
class ModuleBackupInfo:
    module_name: str         # Name of the module
    timestamp: int           # Unix timestamp when backup was created
    description: str         # Human-readable description
    backup_dir: str          # Path to backup directory
    files: List[str]         # List of backed up file paths
    services: List[str]      # List of backed up service names
    databases: List[Dict]    # List of database configurations
    checksum: str            # SHA-256 checksum of backup
```

#### Convenience Functions
```python
from initialization.files.user_local_lib.updates.utils.state_manager import (
    create_state_manager,
    backup_module_simple,
    restore_module_simple
)

# Simple operations with default backup directory
success = backup_module_simple("mymodule", files=["/etc/config.conf"])
success = restore_module_simple("mymodule")

# Custom backup directory
custom_state_manager = create_state_manager("/custom/backup/path")
```

## 🚀 Integration Patterns

### Pattern 1: Simple File Backup (Hotfix Style)
```python
def main(args=None):
    """Simple update with file backup."""
    from initialization.files.user_local_lib.updates.utils import log_message
    from initialization.files.user_local_lib.updates.utils.state_manager import StateManager
    
    state_manager = StateManager("/var/backups/hotfix")
    
    # Backup before changes
    backup_success = state_manager.backup_module_state(
        module_name="hotfix_pool_website_updates",
        files=[
            "/var/www/homeserver/src/components/auth.tsx",
            "/var/www/homeserver/src/components/header.tsx"
        ]
    )
    
    if not backup_success:
        return {"success": False, "error": "Backup failed"}
    
    try:
        # Apply changes
        copy_new_files()
        run_npm_build()
        restart_services()
        
        log_message("Update completed successfully")
        return {"success": True}
        
    except Exception as e:
        log_message(f"Update failed: {e}", "ERROR")
        # Restore backup
        state_manager.restore_module_state("hotfix_pool_website_updates")
        return {"success": False, "error": str(e)}
```

### Pattern 2: Comprehensive Module Update (Website Style)
```python
def main(args=None):
    """Website update with comprehensive backup."""
    from initialization.files.user_local_lib.updates.utils import log_message
    from initialization.files.user_local_lib.updates.utils.state_manager import StateManager
    
    state_manager = StateManager("/var/backups/website")
    
    # Create comprehensive backup
    backup_success = state_manager.backup_module_state(
        module_name="website",
        description="Pre-website-update backup",
        files=[
            "/var/www/homeserver/src",
            "/var/www/homeserver/backend",
            "/var/www/homeserver/premium",
            "/var/www/homeserver/public",
            "/var/www/homeserver/package.json"
        ]
    )
    
    if not backup_success:
        return {"success": False, "error": "Backup creation failed"}
    
    try:
        # Perform update operations
        log_message("Cloning repository")
        clone_repository()
        
        log_message("Updating components")
        update_components()
        
        log_message("Running build process")
        run_npm_build()
        restart_services()
        
        log_message("Website update completed successfully")
        return {"success": True}
        
    except Exception as e:
        log_message(f"Website update failed, rolling back: {e}", "ERROR")
        success = state_manager.restore_module_state("website")
        return {"success": False, "rollback_success": success}
```

### Pattern 3: Service Update with Database
```python
def main(args=None):
    """Service update with database migration."""
    from initialization.files.user_local_lib.updates.utils import log_message
    from initialization.files.user_local_lib.updates.utils.state_manager import StateManager
    
    state_manager = StateManager("/var/backups/myservice")
    
    # Backup files, services, and database
    backup_success = state_manager.backup_module_state(
        module_name="myservice",
        description="Pre-migration backup",
        files=["/etc/myservice/", "/opt/myservice/"],
        services=["myservice", "myservice-worker"],
        databases=[{
            "type": "postgresql",
            "host": "localhost",
            "user": "myservice",
            "database": "myservice_db"
        }]
    )
    
    if not backup_success:
        return {"success": False, "error": "Backup failed"}
    
    try:
        # Perform update with database migration
        log_message("Stopping services")
        stop_services()
        
        log_message("Updating configuration")
        update_configuration()
        
        log_message("Running database migration")
        migrate_database()
        
        log_message("Starting services")
        start_services()
        
        if not verify_service_health():
            raise Exception("Service health check failed")
        
        log_message("Service update completed successfully")
        return {"success": True}
        
    except Exception as e:
        log_message(f"Service update failed, rolling back: {e}", "ERROR")
        success = state_manager.restore_module_state("myservice")
        return {"success": False, "rollback_success": success}
```

### Pattern 4: Using Version Control
```python
def main(args=None):
    """Update using version control rollback."""
    from initialization.files.user_local_lib.updates.utils import log_message
    from initialization.files.user_local_lib.updates.utils.version_control import (
        checkout_module_version,
        list_module_versions
    )
    
    module_name = "mymodule"
    
    try:
        # Check available versions
        versions = list_module_versions(module_name)
        log_message(f"Available versions: {[v['version'] for v in versions]}")
        
        # Perform update operations
        perform_update_operations()
        
        log_message("Update completed successfully")
        return {"success": True}
        
    except Exception as e:
        log_message(f"Update failed, rolling back: {e}", "ERROR")
        
        # Rollback to last safe version
        success = checkout_module_version(module_name)
        
        return {"success": False, "rollback_success": success}
```

## 📁 File Structure

StateManager creates the following structure:

```
/var/backups/updates/
├── module_backups.json             # Module backup index
├── mymodule_backup/                # Module backup directory
│   ├── files/                      # Backed up files
│   │   ├── etc/
│   │   │   └── mymodule/
│   │   │       └── config.conf
│   │   └── opt/
│   │       └── mymodule/
│   ├── services.json               # Service states
│   └── databases/                  # Database backups
│       └── db_0.sql
└── website_backup/                 # Another module backup
    └── files/
        └── var/
            └── www/
                └── homeserver/
```

## 🔧 Error Handling

StateManager includes comprehensive error handling:

```python
from initialization.files.user_local_lib.updates.utils.state_manager import StateManagerError

try:
    backup_success = state_manager.backup_module_state(
        module_name="mymodule",
        files=["/nonexistent/path"]
    )
    if not backup_success:
        log_message("Backup operation failed", "ERROR")
except Exception as e:
    log_message(f"Backup error: {e}", "ERROR")

try:
    success = state_manager.restore_module_state("nonexistent_module")
    if not success:
        log_message("Restore failed - backup not found", "ERROR")
except Exception as e:
    log_message(f"Restore error: {e}", "ERROR")
```

## 🛠️ Best Practices

### 1. Use Consistent Logging
```python
from initialization.files.user_local_lib.updates.utils import log_message

# ✅ Good: Consistent logging with appropriate levels
log_message("Starting update process")
log_message("Backup created successfully")
log_message("Service restart failed", "ERROR")

# ❌ Bad: Inconsistent logging
print("Starting update")  # No timestamp or level
```

### 2. Always Create Backups Before Changes
```python
# ✅ Good: Backup before changes
backup_success = state_manager.backup_module_state("mymodule", files=[...])
if backup_success:
    make_changes()

# ❌ Bad: Changes without backup
make_changes()  # No way to rollback
```

### 3. Use Descriptive Backup Descriptions
```python
# ✅ Good: Descriptive backup descriptions
state_manager.backup_module_state(
    "myservice", 
    description="Pre-security-patch-v2.1.0"
)

# ❌ Bad: Generic descriptions
state_manager.backup_module_state("myservice", description="backup")
```

### 4. Handle Backup and Restore Failures
```python
# ✅ Good: Handle backup failures
backup_success = state_manager.backup_module_state("mymodule", files=[...])
if not backup_success:
    return {"success": False, "error": "Backup creation failed"}

# ✅ Good: Handle restore failures gracefully
try:
    perform_update()
except Exception as e:
    log_message(f"Update failed: {e}", "ERROR")
    
    restore_success = state_manager.restore_module_state("mymodule")
    if not restore_success:
        log_message("CRITICAL: Restore failed! Manual intervention required", "ERROR")
    
    return {"success": False, "restore_success": restore_success}
```

### 5. Single Backup Per Module Philosophy
```python
# ✅ Good: Embrace single backup per module
state_manager.backup_module_state("mymodule", ...)  # Clobbers previous backup
perform_update()

# ❌ Bad: Trying to manage multiple backups
# StateManager doesn't support this - use version control instead
```

## 🔗 Quick Reference

### Essential Imports
```python
# Basic logging
from initialization.files.user_local_lib.updates.utils import log_message

# Version control
from initialization.files.user_local_lib.updates.utils.version_control import (
    checkout_module_version,
    list_module_versions,
    checkout_last_safe
)

# State management
from initialization.files.user_local_lib.updates.utils.state_manager import StateManager

# Convenience functions
from initialization.files.user_local_lib.updates.utils.state_manager import (
    backup_module_simple,
    restore_module_simple,
    create_state_manager
)
```

### Common Operations
```python
# Logging
log_message("Operation completed successfully")
log_message("Error occurred", "ERROR")

# Simple module backup and restore
state_manager = StateManager()
state_manager.backup_module_state("mymodule", files=["/etc/config.conf"])
success = state_manager.restore_module_state("mymodule")

# Version control rollback
success = checkout_module_version("mymodule", "1.0.0")

# Check backup status
has_backup = state_manager.has_backup("mymodule")
backup_info = state_manager.get_backup_info("mymodule")
```

## 📊 Dependencies

The utilities use only Python standard library modules:
- `datetime` - Timestamp formatting
- `sys` - System operations
- `os` - Operating system interface
- `json` - JSON data handling
- `subprocess` - External command execution
- `shutil` - File operations
- `time` - Time utilities
- `hashlib` - Checksum calculation
- `pathlib` - Path manipulation
- `typing` - Type hints
- `dataclasses` - Data class definitions

No external dependencies are required, ensuring system reliability and minimal setup requirements.

## 🎯 Summary

The updates system utilities provide three complementary approaches:

1. **Basic Logging** (`index.py`): Simple, consistent logging for all modules
2. **Version Control** (`version_control.py`): Git-based module version management with tags
3. **State Manager** (`state_manager.py`): Simple single-backup-per-module state management

Choose the appropriate utility based on your update module's needs:
- Use **logging** in all modules for consistent output
- Use **version control** for module-level version rollbacks using Git tags
- Use **state manager** for simple backup/restore operations during updates

All utilities follow the same principles: simplicity, reliability, and comprehensive error handling to ensure robust update operations across the HOMESERVER system. 