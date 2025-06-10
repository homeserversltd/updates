# Updates System Utilities

## Overview

This directory contains utility modules that support the schema-driven updates orchestration system. The utilities provide shared functionality for logging, version rollback, and comprehensive backup/restore operations that can be used across all update modules.

## Key Components

### Core Utilities (`__init__.py`)
Provides easy imports for commonly used utilities:
```python
from .index import log_message
from .rollback import rollback_module, list_available_versions, rollback_to_last_safe
```

### Logging Utility (`index.py`)
Simple, consistent logging functionality for all update modules.

### Legacy Rollback (`rollback.py`) 
Git-based rollback system for version management using Git tags and manifest tracking.

### Global Rollback System (`global_rollback.py`)
Comprehensive backup and rollback utility providing advanced features like file/service/database backups with atomic operations.

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

## 🔄 Legacy Rollback System (`rollback.py`)

Git-based rollback system that uses tags and manifest version tracking.

### rollback_module()
```python
from initialization.files.user_local_lib.updates.utils import rollback_module

# Rollback to lastSafeVersion from manifest
success = rollback_module("adblock")

# Rollback to specific version
success = rollback_module("adblock", target_version="1.0.0")
```

**Parameters:**
- `module_name` (str): Name of the module to rollback
- `target_version` (str, optional): Specific version to rollback to

**Returns:** `bool` - True if successful

### list_available_versions()
```python
from initialization.files.user_local_lib.updates.utils import list_available_versions

versions = list_available_versions("adblock")
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

### rollback_to_last_safe()
```python
from initialization.files.user_local_lib.updates.utils import rollback_to_last_safe

# Convenience function - rollback to lastSafeVersion
success = rollback_to_last_safe("adblock")
```

**Git Tag Convention:**
```
<module_name>-v<version>-<timestamp>
# Examples:
adblock-v1.0.0-20240610
gogs-v2.1.3-20241208
```

## 🛡️ Global Rollback System (`global_rollback.py`)

Comprehensive backup and rollback utility for advanced update operations.

### Key Features
- **File and Directory Backups**: Complete backup with checksums
- **Service State Management**: Backup/restore systemd service states
- **Database Backups**: Support for PostgreSQL and SQLite
- **Atomic Operations**: Rollback points for complex updates
- **Automatic Cleanup**: Remove old backups with retention policies
- **Emergency Recovery**: Standalone rollback capabilities

### Basic Usage

#### GlobalRollback Class
```python
from initialization.files.user_local_lib.updates.utils.global_rollback import GlobalRollback

# Create rollback instance
rollback = GlobalRollback("/var/backups/updates")

# Backup a file
backup_info = rollback.backup_file(
    source_path="/etc/myservice/config.conf",
    description="pre_update_v2.1.0",
    module_name="myservice"
)

# Restore from backup
success = rollback.restore_backup(backup_info.backup_id)
```

#### File Operations
```python
# Backup single file
file_backup = rollback.backup_file("/etc/config.conf", "pre_update", "mymodule")

# Backup entire directory
dir_backup = rollback.backup_file("/opt/myapp/", "pre_update", "mymodule")

# Restore any backup
success = rollback.restore_backup(file_backup.backup_id)
```

#### Service Operations
```python
# Backup service states
service_backup = rollback.backup_services(
    services=["nginx", "postgresql", "myservice"],
    description="pre_update",
    module_name="mymodule"
)

# Restore service states (enabled/disabled, active/inactive)
success = rollback.restore_backup(service_backup.backup_id)
```

#### Database Operations
```python
# PostgreSQL backup
postgres_backup = rollback.backup_database(
    db_config={
        "type": "postgresql",
        "host": "localhost",
        "port": "5432", 
        "user": "myapp",
        "password": "mypass",  # Optional
        "database": "myapp_db"
    },
    description="pre_migration",
    module_name="myapp"
)

# SQLite backup
sqlite_backup = rollback.backup_database(
    db_config={
        "type": "sqlite",
        "database": "/var/lib/myapp/data.db"
    },
    description="pre_update",
    module_name="myapp"
)
```

### Rollback Points (Recommended)

Create comprehensive rollback points for complex operations:

```python
# Create rollback point
rollback_point = rollback.create_rollback_point(
    module_name="myservice",
    description="major_update_v3.0",
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
    # Restore entire rollback point
    success = rollback.restore_rollback_point(rollback_point)
```

### Backup Management

#### List Backups
```python
# List all backups
all_backups = rollback.list_backups()

# List backups for specific module
module_backups = rollback.list_backups(module_name="myservice")

# List only file backups
file_backups = rollback.list_backups(backup_type="file")

# Print backup details
for backup in all_backups:
    print(f"ID: {backup.backup_id}")
    print(f"Type: {backup.backup_type}")
    print(f"Module: {backup.metadata['module_name']}")
    print(f"Created: {time.ctime(backup.timestamp)}")
    print(f"Description: {backup.description}")
```

#### Cleanup Old Backups
```python
# Remove backups older than 30 days, keep minimum 5 per module
removed_count = rollback.cleanup_old_backups(
    max_age_days=30,
    keep_minimum=5
)
log_message(f"Cleaned up {removed_count} old backups")
```

### Data Classes

#### BackupInfo
```python
@dataclass
class BackupInfo:
    backup_id: str           # Unique backup identifier
    timestamp: int           # Unix timestamp
    backup_type: str         # 'file', 'service', 'database'
    description: str         # Human-readable description
    source_path: str         # Original path/identifier
    backup_path: str         # Path to backup data
    metadata: Dict[str, Any] # Additional metadata
    checksum: str            # SHA-256 checksum
```

#### Convenience Functions
```python
from initialization.files.user_local_lib.updates.utils.global_rollback import (
    create_global_rollback,
    backup_file_simple,
    restore_backup_simple
)

# Simple operations
backup_id = backup_file_simple("/etc/config.conf", "pre_update", "mymodule")
success = restore_backup_simple(backup_id)

# Custom backup directory
custom_rollback = create_global_rollback("/custom/backup/path")
```

## 🚀 Integration Patterns

### Pattern 1: Simple Update Module
```python
def main(args=None):
    """Simple update with file backup."""
    from initialization.files.user_local_lib.updates.utils import log_message
    from initialization.files.user_local_lib.updates.utils.global_rollback import GlobalRollback
    
    rollback = GlobalRollback()
    config_file = "/etc/myservice/config.conf"
    
    # Backup before changes
    backup = rollback.backup_file(config_file, "config_update", "myservice")
    
    try:
        # Update configuration
        update_config_file(config_file)
        log_message("Configuration updated successfully")
        return {"success": True}
        
    except Exception as e:
        log_message(f"Update failed: {e}", "ERROR")
        # Restore backup
        rollback.restore_backup(backup.backup_id)
        return {"success": False, "error": str(e)}
```

### Pattern 2: Service Update with Rollback
```python
def main(args=None):
    """Service update with comprehensive rollback."""
    from initialization.files.user_local_lib.updates.utils import log_message
    from initialization.files.user_local_lib.updates.utils.global_rollback import GlobalRollback
    
    rollback = GlobalRollback()
    
    # Create comprehensive rollback point
    rollback_point = rollback.create_rollback_point(
        module_name="myservice",
        description="service_update_v2.1.0",
        files=["/etc/myservice/", "/opt/myservice/bin/"],
        services=["myservice", "myservice-worker"]
    )
    
    try:
        # Perform update operations
        log_message("Stopping services")
        stop_services()
        
        log_message("Updating binaries")
        update_binaries()
        
        log_message("Updating configuration") 
        update_configuration()
        
        log_message("Starting services")
        start_services()
        
        log_message("Verifying service health")
        if not verify_service_health():
            raise Exception("Service health check failed")
        
        log_message("Service update completed successfully")
        return {"success": True}
        
    except Exception as e:
        log_message(f"Service update failed, rolling back: {e}", "ERROR")
        success = rollback.restore_rollback_point(rollback_point)
        return {"success": False, "rollback_success": success}
```

### Pattern 3: Using Legacy Rollback
```python
def main(args=None):
    """Update using legacy Git-based rollback."""
    from initialization.files.user_local_lib.updates.utils import (
        log_message, 
        rollback_module,
        list_available_versions
    )
    
    module_name = "mymodule"
    
    try:
        # Check available versions
        versions = list_available_versions(module_name)
        log_message(f"Available versions: {[v['version'] for v in versions]}")
        
        # Perform update operations
        perform_update_operations()
        
        log_message("Update completed successfully")
        return {"success": True}
        
    except Exception as e:
        log_message(f"Update failed, rolling back: {e}", "ERROR")
        
        # Rollback to last safe version
        success = rollback_module(module_name)
        
        return {"success": False, "rollback_success": success}
```

## 📁 File Structure

The utilities create the following structure:

```
/var/backups/updates/
├── backups_index.json              # Global rollback index
├── operations.log                  # Operations log
├── abc123def456_config.conf        # File backup
├── def456ghi789_services.json      # Service state backup
├── ghi789jkl012_db.sql            # Database backup
└── jkl012mno345_myapp/            # Directory backup
    └── ...
```

## 🔧 Error Handling

All utilities include comprehensive error handling:

```python
from initialization.files.user_local_lib.updates.utils.global_rollback import GlobalRollbackError

try:
    backup = rollback.backup_file("/nonexistent/path", "test", "mymodule")
except GlobalRollbackError as e:
    log_message(f"Backup operation failed: {e}", "ERROR")
    # Handle appropriately

try:
    success = rollback.restore_backup("invalid_backup_id")
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
log_message("Configuration validated successfully")
log_message("Service restart failed", "ERROR")
log_message("Backup created successfully")

# ❌ Bad: Inconsistent logging
print("Starting update")  # No timestamp or level
```

### 2. Choose Appropriate Rollback Method
```python
# ✅ Good: Use global rollback for complex operations
rollback_point = rollback.create_rollback_point(...)

# ✅ Good: Use legacy rollback for version management
success = rollback_module("mymodule", "1.0.0")

# ❌ Bad: Mixing rollback methods inconsistently
```

### 3. Always Create Backups Before Changes
```python
# ✅ Good: Backup before changes
backup = rollback.backup_file(config_file, "pre_update", "mymodule")
make_changes()

# ❌ Bad: Changes without backup
make_changes()  # No way to rollback
```

### 4. Use Descriptive Backup Names
```python
# ✅ Good: Descriptive backup descriptions
rollback.backup_file(config_file, "pre_security_patch_v2.1.0", "myservice")

# ❌ Bad: Generic descriptions
rollback.backup_file(config_file, "backup", "myservice")
```

### 5. Handle Rollback Failures
```python
# ✅ Good: Handle rollback failures gracefully
try:
    perform_update()
except Exception as e:
    log_message(f"Update failed: {e}", "ERROR")
    
    rollback_success = rollback.restore_rollback_point(rollback_point)
    if not rollback_success:
        log_message("CRITICAL: Rollback failed! Manual intervention required", "ERROR")
    
    return {"success": False, "rollback_success": rollback_success}
```

## 🔗 Quick Reference

### Essential Imports
```python
# Basic logging
from initialization.files.user_local_lib.updates.utils import log_message

# Legacy rollback
from initialization.files.user_local_lib.updates.utils import (
    rollback_module,
    list_available_versions,
    rollback_to_last_safe
)

# Global rollback system
from initialization.files.user_local_lib.updates.utils.global_rollback import GlobalRollback

# Convenience functions
from initialization.files.user_local_lib.updates.utils.global_rollback import (
    backup_file_simple,
    restore_backup_simple,
    create_global_rollback
)
```

### Common Operations
```python
# Logging
log_message("Operation completed successfully")
log_message("Error occurred", "ERROR")

# Simple file backup and restore
backup_id = backup_file_simple("/etc/config.conf", "pre_update", "mymodule")
success = restore_backup_simple(backup_id)

# Legacy version rollback
success = rollback_module("mymodule", "1.0.0")

# Comprehensive rollback point
rollback = GlobalRollback()
rollback_point = rollback.create_rollback_point("mymodule", "update", files=[...], services=[...])
success = rollback.restore_rollback_point(rollback_point)
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
- `tempfile` - Temporary file handling

No external dependencies are required, ensuring system reliability and minimal setup requirements.

## 🎯 Summary

The updates system utilities provide three complementary approaches:

1. **Basic Logging** (`index.py`): Simple, consistent logging for all modules
2. **Legacy Rollback** (`rollback.py`): Git-based version management with tags
3. **Global Rollback** (`global_rollback.py`): Comprehensive backup/restore for complex operations

Choose the appropriate utility based on your update module's needs:
- Use **logging** in all modules for consistent output
- Use **legacy rollback** for version-based rollbacks using Git tags
- Use **global rollback** for complex operations requiring file/service/database backups

All utilities follow the same principles: simplicity, reliability, and comprehensive error handling to ensure robust update operations across the HOMESERVER system. 