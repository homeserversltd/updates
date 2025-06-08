# Global Rollback Utility for Updates System

The Global Rollback Utility provides comprehensive backup and rollback capabilities that can be used across all update modules in the HOMESERVER system. It extracts and generalizes the advanced rollback features from the hotfix system, making them available to any module that needs reliable backup and restore functionality.

## 🎯 Overview

This utility enables update modules to:
- Create atomic backups before making changes
- Restore from backups if operations fail
- Manage service states during updates
- Handle database backups and restores
- Create comprehensive rollback points
- Clean up old backups automatically

## 📁 Key Components

- **`GlobalRollback`**: Main class providing all rollback functionality
- **`BackupInfo`**: Data class containing backup metadata
- **`RollbackOperation`**: Data class for rollback operation definitions
- **Convenience functions**: Simple wrappers for common operations

## 🚀 Quick Start

### Basic Usage in Update Modules

```python

def main(args=None):
    """Example update module using global rollback."""
    rollback = GlobalRollback()
    
    # Create backups before making changes
    config_backup = rollback.backup_file("/etc/myservice/config.conf", "pre_update", "myservice")
    service_backup = rollback.backup_services(["myservice"], "pre_update", "myservice")
    
    try:
        # Perform your update operations here
        update_config_file()
        restart_service()
        
        log_message("Update completed successfully")
        return {"success": True}
        
    except Exception as e:
        log_message(f"Update failed: {e}", "ERROR")
        
        # Restore from backups
        rollback.restore_backup(config_backup.backup_id)
        rollback.restore_backup(service_backup.backup_id)
        
        return {"success": False, "error": str(e)}
```

### Using Rollback Points (Recommended)

```python

def main(args=None):
    """Example using comprehensive rollback points."""
    rollback = GlobalRollback()
    
    # Create a comprehensive rollback point
    rollback_point = rollback.create_rollback_point(
        module_name="myservice",
        description="pre_update_v2.1.0",
        files=[
            "/etc/myservice/config.conf",
            "/opt/myservice/data",
            "/var/lib/myservice/settings.json"
        ],
        services=["myservice", "myservice-worker"],
        databases=[{
            "type": "postgresql",
            "host": "localhost",
            "user": "myservice",
            "database": "myservice_db"
        }]
    )
    
    try:
        # Perform complex update operations
        update_configuration()
        migrate_database()
        update_binaries()
        restart_services()
        
        log_message("Update completed successfully")
        return {"success": True, "rollback_point": rollback_point}
        
    except Exception as e:
        log_message(f"Update failed, rolling back: {e}", "ERROR")
        
        # Restore entire rollback point
        success = rollback.restore_rollback_point(rollback_point)
        
        return {
            "success": False, 
            "error": str(e),
            "rollback_success": success
        }
```

## 📋 Detailed API Reference

### GlobalRollback Class

#### Constructor
```python
rollback = GlobalRollback(backup_dir="/var/backups/updates")
```

**Parameters:**
- `backup_dir` (str): Directory to store backups (default: `/var/backups/updates`)

#### File Operations

##### backup_file()
```python
backup_info = rollback.backup_file(
    source_path="/etc/config.conf",
    description="pre_update", 
    module_name="mymodule"
)
```

**Parameters:**
- `source_path` (str): Path to file or directory to backup
- `description` (str): Description of the backup
- `module_name` (str): Name of the module creating the backup

**Returns:** `BackupInfo` object with backup details

##### restore_backup()
```python
success = rollback.restore_backup(backup_info.backup_id)
```

**Parameters:**
- `backup_id` (str): ID of the backup to restore

**Returns:** `bool` - True if successful, False otherwise

#### Service Operations

##### backup_services()
```python
service_backup = rollback.backup_services(
    services=["nginx", "postgresql", "myservice"],
    description="pre_update",
    module_name="mymodule"
)
```

**Parameters:**
- `services` (List[str]): List of systemd service names
- `description` (str): Description of the backup
- `module_name` (str): Name of the module creating the backup

**Returns:** `BackupInfo` object with service state backup

#### Database Operations

##### backup_database()
```python
# PostgreSQL example
db_backup = rollback.backup_database(
    db_config={
        "type": "postgresql",
        "host": "localhost",
        "port": "5432",
        "user": "dbuser",
        "password": "dbpass",  # Optional, can use .pgpass
        "database": "mydb"
    },
    description="pre_migration",
    module_name="mymodule"
)

# SQLite example
sqlite_backup = rollback.backup_database(
    db_config={
        "type": "sqlite",
        "database": "/var/lib/myapp/database.db"
    },
    description="pre_update",
    module_name="mymodule"
)
```

#### Rollback Points

##### create_rollback_point()
```python
rollback_point = rollback.create_rollback_point(
    module_name="mymodule",
    description="comprehensive_backup_v1.2.0",
    files=["/etc/config.conf", "/opt/myapp"],
    services=["myservice"],
    databases=[db_config]
)
```

**Returns:** `Dict[str, str]` mapping backup types to backup IDs

##### restore_rollback_point()
```python
success = rollback.restore_rollback_point(rollback_point)
```

**Parameters:**
- `rollback_point` (Dict[str, str]): Rollback point returned by `create_rollback_point()`

**Returns:** `bool` - True if all restores successful

#### Utility Operations

##### list_backups()
```python
# List all backups
all_backups = rollback.list_backups()

# List backups for specific module
module_backups = rollback.list_backups(module_name="mymodule")

# List only file backups
file_backups = rollback.list_backups(backup_type="file")
```

##### cleanup_old_backups()
```python
removed_count = rollback.cleanup_old_backups(
    max_age_days=30,    # Remove backups older than 30 days
    keep_minimum=5      # But keep at least 5 backups per module
)
```

## 🔧 Integration Patterns

### Pattern 1: Simple File Backup

```python
def update_config_file():
    """Simple pattern for backing up a single file."""
    from initialization.files.user_local_lib.updates.utils.global_rollback import GlobalRollback
    
    rollback = GlobalRollback()
    config_path = "/etc/myservice/config.conf"
    
    # Backup before changes
    backup = rollback.backup_file(config_path, "config_update", "myservice")
    
    try:
        # Make changes
        with open(config_path, 'w') as f:
            f.write(new_config_content)
        
        return True
        
    except Exception as e:
        # Restore on failure
        rollback.restore_backup(backup.backup_id)
        raise e
```

### Pattern 2: Service Update with Rollback

```python
def update_service_with_rollback():
    """Pattern for updating a service with automatic rollback."""
    from initialization.files.user_local_lib.updates.utils.global_rollback import GlobalRollback
    
    rollback = GlobalRollback()
    
    # Create comprehensive backup
    rollback_point = rollback.create_rollback_point(
        module_name="myservice",
        description="service_update",
        files=["/etc/myservice/", "/opt/myservice/bin/"],
        services=["myservice"]
    )
    
    try:
        # Stop service
        subprocess.run(["systemctl", "stop", "myservice"], check=True)
        
        # Update files
        update_binary_files()
        update_configuration()
        
        # Start service
        subprocess.run(["systemctl", "start", "myservice"], check=True)
        
        # Verify service is working
        if not verify_service_health():
            raise Exception("Service health check failed")
        
        return {"success": True}
        
    except Exception as e:
        log_message(f"Service update failed, rolling back: {e}", "ERROR")
        rollback.restore_rollback_point(rollback_point)
        return {"success": False, "error": str(e)}
```

### Pattern 3: Database Migration with Backup

```python
def migrate_database():
    """Pattern for database migrations with backup."""
    
    rollback = GlobalRollback()
    
    db_config = {
        "type": "postgresql",
        "host": "localhost",
        "user": "myapp",
        "database": "myapp_db"
    }
    
    # Backup database before migration
    db_backup = rollback.backup_database(
        db_config, 
        "pre_migration_v2.0", 
        "myapp"
    )
    
    try:
        # Run migration
        run_database_migration()
        
        # Verify migration
        if not verify_database_schema():
            raise Exception("Database schema verification failed")
        
        return {"success": True}
        
    except Exception as e:
        log_message(f"Migration failed, restoring database: {e}", "ERROR")
        rollback.restore_backup(db_backup.backup_id)
        return {"success": False, "error": str(e)}
```

### Pattern 4: Complex Multi-Component Update

```python
def complex_system_update():
    """Pattern for complex updates involving multiple components."""
    
    rollback = GlobalRollback()
    
    # Create comprehensive rollback point
    rollback_point = rollback.create_rollback_point(
        module_name="complex_system",
        description="major_update_v3.0",
        files=[
            "/etc/myapp/",
            "/opt/myapp/",
            "/var/lib/myapp/config/"
        ],
        services=[
            "myapp-web",
            "myapp-worker", 
            "myapp-scheduler",
            "nginx"
        ],
        databases=[
            {
                "type": "postgresql",
                "host": "localhost",
                "user": "myapp",
                "database": "myapp_main"
            },
            {
                "type": "sqlite",
                "database": "/var/lib/myapp/cache.db"
            }
        ]
    )
    
    try:
        # Phase 1: Stop services
        log_message("Phase 1: Stopping services")
        stop_all_services()
        
        # Phase 2: Update binaries
        log_message("Phase 2: Updating binaries")
        update_application_binaries()
        
        # Phase 3: Migrate databases
        log_message("Phase 3: Migrating databases")
        migrate_main_database()
        migrate_cache_database()
        
        # Phase 4: Update configuration
        log_message("Phase 4: Updating configuration")
        update_configuration_files()
        
        # Phase 5: Start services
        log_message("Phase 5: Starting services")
        start_all_services()
        
        # Phase 6: Verify system health
        log_message("Phase 6: Verifying system health")
        if not verify_system_health():
            raise Exception("System health verification failed")
        
        log_message("Complex update completed successfully")
        return {"success": True, "rollback_point": rollback_point}
        
    except Exception as e:
        log_message(f"Complex update failed at phase, rolling back: {e}", "ERROR")
        
        # Restore everything
        success = rollback.restore_rollback_point(rollback_point)
        
        return {
            "success": False,
            "error": str(e),
            "rollback_success": success
        }
```

## 🔍 Convenience Functions


```python
from initialization.files.user_local_lib.updates.utils.global_rollback import (
    backup_file_simple,
    restore_backup_simple,
    create_global_rollback
)

# Simple file backup
backup_id = backup_file_simple("/etc/config.conf", "quick_backup", "mymodule")

# Simple restore
success = restore_backup_simple(backup_id)

# Create custom rollback instance
custom_rollback = create_global_rollback("/custom/backup/path")
```

## 📊 Backup Management

### Listing Backups

```python
# List all backups
all_backups = rollback.list_backups()
for backup in all_backups:
    print(f"ID: {backup.backup_id}")
    print(f"Module: {backup.metadata['module_name']}")
    print(f"Type: {backup.backup_type}")
    print(f"Created: {time.ctime(backup.timestamp)}")
    print(f"Description: {backup.description}")
    print()

# List backups for specific module
module_backups = rollback.list_backups(module_name="myservice")

# List only service backups
service_backups = rollback.list_backups(backup_type="service")
```

### Cleaning Up Old Backups

```python
# Clean up backups older than 30 days, keeping minimum 5 per module
removed = rollback.cleanup_old_backups(max_age_days=30, keep_minimum=5)
log_message(f"Cleaned up {removed} old backups")
```

## 🛡️ Best Practices

### 1. Always Create Backups Before Changes
```python
# ✅ Good: Create backup before making changes
backup = rollback.backup_file(config_path, "pre_update", module_name)
make_changes()

# ❌ Bad: Make changes without backup
make_changes()  # No way to rollback if this fails
```

### 2. Use Descriptive Backup Names
```python
# ✅ Good: Descriptive names with version/context
rollback.backup_file(config_path, "pre_update_v2.1.0_security_patch", "myservice")

# ❌ Bad: Generic names
rollback.backup_file(config_path, "backup", "myservice")
```

### 3. Use Rollback Points for Complex Operations
```python
# ✅ Good: Comprehensive rollback point
rollback_point = rollback.create_rollback_point(
    module_name="myservice",
    description="major_update_v2.0",
    files=[config_path, data_dir],
    services=["myservice"],
    databases=[db_config]
)

# ❌ Bad: Individual backups that might get out of sync
config_backup = rollback.backup_file(config_path, "update", "myservice")
service_backup = rollback.backup_services(["myservice"], "update", "myservice")
# If restore fails partially, system could be in inconsistent state
```

### 4. Handle Rollback Failures Gracefully
```python
try:
    # Attempt update
    perform_update()
except Exception as e:
    log_message(f"Update failed: {e}", "ERROR")
    
    # Attempt rollback
    rollback_success = rollback.restore_rollback_point(rollback_point)
    
    if not rollback_success:
        log_message("CRITICAL: Rollback failed! Manual intervention required", "ERROR")
        # Log detailed information for manual recovery
        log_rollback_details(rollback_point)
    
    return {"success": False, "rollback_success": rollback_success}
```

### 5. Clean Up Backups Regularly
```python
# Add to your module's maintenance routine
def cleanup_old_backups():
    """Clean up old backups as part of regular maintenance."""
    rollback = GlobalRollback()
    removed = rollback.cleanup_old_backups(max_age_days=30, keep_minimum=5)
    log_message(f"Maintenance: Cleaned up {removed} old backups")
```

## 🚨 Error Handling

The global rollback utility provides comprehensive error handling:

```python
from initialization.files.user_local_lib.updates.utils.global_rollback import GlobalRollbackError

try:
    backup = rollback.backup_file("/nonexistent/path", "test", "mymodule")
except GlobalRollbackError as e:
    log_message(f"Backup failed: {e}", "ERROR")
    # Handle backup failure appropriately

try:
    success = rollback.restore_backup("invalid_backup_id")
    if not success:
        log_message("Restore failed - backup not found or corrupted", "ERROR")
except Exception as e:
    log_message(f"Restore error: {e}", "ERROR")
```

## 📁 File Structure

The global rollback utility creates the following structure:

```
/var/backups/updates/
├── backups_index.json          # Index of all backups
├── operations.log              # Log of all operations
├── abc123def456_config.conf    # File backup
├── def456ghi789_services.json  # Service state backup
├── ghi789jkl012_db.sql        # Database backup
└── jkl012mno345_myapp/        # Directory backup
    └── ...
```

## 🔗 Integration with Existing Modules

To integrate the global rollback utility into existing update modules:

1. **Import the utility:**
```python
from initialization.files.user_local_lib.updates.utils.global_rollback import GlobalRollback
```

2. **Replace existing backup logic:**
```python
# Old pattern
def backup_create(service_name, path, ext):
    backup_path = path + ext
    shutil.copy2(path, backup_path)
    return backup_path

# New pattern
rollback = GlobalRollback()
backup_info = rollback.backup_file(path, "pre_update", service_name)
```

3. **Update restore logic:**
```python
# Old pattern
def backup_restore(service_name, path, ext):
    backup_path = path + ext
    shutil.copy2(backup_path, path)

# New pattern
success = rollback.restore_backup(backup_info.backup_id)
```

4. **Use rollback points for comprehensive updates:**
```python
# Replace multiple individual backups with rollback points
rollback_point = rollback.create_rollback_point(
    module_name=service_name,
    description="update_operation",
    files=[config_file, data_dir],
    services=[service_name]
)
```

This global rollback utility provides a robust, consistent, and feature-rich backup and restore system that can be used across all update modules in the HOMESERVER system, ensuring reliable rollback capabilities and reducing code duplication. 