# Hotfix Module - Emergency Patch Management System

The Hotfix module provides comprehensive emergency patch capabilities for HOMESERVER systems with advanced rollback and dependency management for critical system patches.

## 🎯 Overview

This module enables rapid deployment of emergency fixes across homeserver infrastructure with guaranteed rollback capabilities, even for one-way operations like database migrations.

### Key Features

- **Schema-version driven updates** - Integrates with global update orchestrator
- **Four operation types**: copy, append, symlink, execute
- **Advanced rollback system** - Handles one-way operations and complex dependencies
- **State capture and restoration** - File, database, service, and system snapshots
- **Emergency independence** - Standalone rollback script for crisis situations
- **Atomic operations** - All-or-nothing execution with automatic rollback on failure

## 📁 Module Structure

```
hotfix/
├── __init__.py              # Module interface and exports
├── index.json               # Operation definitions and configuration
├── index.py                 # Main hotfix orchestration engine
├── rollback.py              # Advanced rollback management system
├── rollback_standalone.py   # Emergency standalone rollback script
├── readme.md               # This documentation
└── src/                    # Source files for hotfix operations
    ├── example.sh
    ├── fixed_script.py
    └── emergency_patch.conf
```

## 🚀 Quick Start

### 1. Basic Hotfix Application

```bash
# Apply all enabled hotfixes
python3 /usr/local/lib/user_local_lib/updates/hotfix/index.py

# Check status without applying
python3 /usr/local/lib/user_local_lib/updates/hotfix/index.py --check

# Manual rollback
python3 /usr/local/lib/user_local_lib/updates/hotfix/index.py --rollback
```

### 2. Emergency Rollback (Standalone)

```bash
# List available snapshots
python3 rollback_standalone.py --list-snapshots

# Restore specific snapshot
python3 rollback_standalone.py --restore-snapshot abc123def456

# Emergency rollback from operation log
python3 rollback_standalone.py --rollback-log /var/log/hotfix_operations.json
```

## 📋 Configuration (`index.json`)

### Basic Structure

```json
{
    "metadata": {
        "schema_version": "1.0.0",
        "description": "Emergency hotfixes and critical patches",
        "priority": "critical"
    },
    "config": {
        "backup_dir": "/var/backups/hotfix",
        "log_file": "/var/log/homeserver/hotfix.log",
        "rollback_on_failure": true
    },
    "operations": [
        // Operation definitions here
    ],
    "validation": {
        "pre_checks": [
            // Pre-execution validation
        ],
        "post_checks": [
            // Post-execution validation
        ]
    }
}
```

### Operation Types

#### 1. Copy Operation
Replace files with automatic backup:

```json
{
    "id": "fix_auth_module",
    "type": "copy",
    "source": "fixed_auth.py",
    "target": "/var/www/homeserver/backend/auth.py",
    "description": "Replace broken authentication module",
    "backup": true,
    "permissions": {
        "user": "www-data",
        "group": "www-data",
        "mode": "644"
    },
    "enabled": true
}
```

#### 2. Append Operation
Add content to files with markers for clean removal:

```json
{
    "id": "add_security_headers",
    "type": "append",
    "source": "security_headers.conf",
    "target": "/etc/nginx/nginx.conf",
    "description": "Add security headers to nginx config",
    "identifier": "security_patch_001",
    "marker": "# HOTFIX SECURITY HEADERS",
    "backup": true,
    "enabled": true
}
```

#### 3. Symlink Operation
Create symbolic links with backup of existing targets:

```json
{
    "id": "link_patched_binary",
    "type": "symlink",
    "source": "patched_binary_v2",
    "target": "/usr/local/bin/homeserver-tool",
    "description": "Link to patched binary",
    "backup": true,
    "permissions": {
        "mode": "755"
    },
    "enabled": true
}
```

#### 4. Execute Operation
Run scripts with cleanup and timeout control:

```json
{
    "id": "emergency_db_repair",
    "type": "execute",
    "source": "repair_database.sh",
    "description": "Run emergency database repair",
    "working_dir": "/tmp",
    "timeout": 300,
    "cleanup_after": true,
    "rollback_script": "rollback_db_repair.sh",
    "enabled": true
}
```

### Advanced Features

#### Phase-Based Execution
For operations that must happen in specific order:

```json
{
    "id": "stop_services",
    "type": "execute",
    "source": "stop_services.sh",
    "phase": 1,
    "dependencies": [],
    "critical": true
},
{
    "id": "update_config",
    "type": "copy",
    "source": "new_config.json",
    "target": "/etc/homeserver/config.json",
    "phase": 2,
    "dependencies": ["stop_services"],
    "backup": true
},
{
    "id": "restart_services",
    "type": "execute",
    "source": "restart_services.sh",
    "phase": 3,
    "dependencies": ["update_config"]
}
```

#### Pre/Post Validation
Ensure system health before and after operations:

```json
"validation": {
    "pre_checks": [
        {
            "command": "systemctl is-active homeserver",
            "expected": "active",
            "description": "Ensure homeserver is running"
        }
    ],
    "post_checks": [
        {
            "command": "curl -s -o /dev/null -w '%{http_code}' http://localhost:5000/health",
            "expected": "200",
            "description": "Check web interface responds"
        }
    ]
}
```

## 🛡️ Rollback System

### Automatic Rollback
The system automatically creates backups and can rollback on failure:

```python
from hotfix import HotfixManager

manager = HotfixManager("/path/to/hotfix/module")
result = manager.apply_hotfixes()

if not result["success"]:
    # Automatic rollback already occurred if rollback_on_failure=true
    print(f"Hotfix failed: {result['error']}")
```

### State Capture
For one-way operations, capture system state first:

```python
from hotfix import StateCapture

state_capture = StateCapture("/var/backups/hotfix")

# Capture different types of state
file_snapshot = state_capture.capture_file_state("/etc/config", "pre_update")
db_snapshot = state_capture.capture_database_state({
    "type": "postgresql",
    "host": "localhost",
    "database": "homeserver",
    "user": "postgres"
}, "pre_migration")
service_snapshot = state_capture.capture_service_state(
    ["homeserver", "nginx", "postgresql"], 
    "pre_maintenance"
)
```

### Emergency Rollback
When the main system is compromised:

```bash
# Use standalone script
python3 rollback_standalone.py --rollback-log /var/log/hotfix_operations.json

# Or restore from snapshot
python3 rollback_standalone.py --restore-snapshot abc123def456
```

## 🔧 Integration with Update System

### Schema Version Detection
The global update orchestrator detects changes via `schema_version`:

```json
{
    "metadata": {
        "schema_version": "1.2.3"  // Bump this to trigger updates
    }
}
```

### Update Flow
1. Git pulls updates repository
2. Compares `schema_version` in `hotfix/index.json`
3. Clobbers entire hotfix directory if newer version found
4. Runs `hotfix/index.py` to apply new operations
5. Operations handle their own configuration changes

## 📊 Monitoring and Logging

### Log Files
- **Main log**: `/var/log/homeserver/hotfix.log`
- **Operation log**: `/var/backups/hotfix/operations.json`
- **Rollback log**: `/var/backups/hotfix/rollback.log`

### Status Checking
```bash
# Check hotfix status
python3 index.py --check

# List available snapshots
python3 rollback.py --list-snapshots

# View recent operations
tail -f /var/log/homeserver/hotfix.log
```

## 🚨 Emergency Procedures

### System Compromised
If the main hotfix system is broken:

1. **Use standalone rollback script**:
   ```bash
   python3 rollback_standalone.py --list-snapshots
   python3 rollback_standalone.py --restore-snapshot <latest_good_snapshot>
   ```

2. **Manual file restoration**:
   ```bash
   # Backups are stored in timestamped directories
   ls /var/backups/hotfix/
   cp /var/backups/hotfix/operation_id_filename_timestamp /original/location
   ```

### Database Recovery
For database issues:

1. **Find database snapshots**:
   ```bash
   ls /var/backups/hotfix/snapshots/*.sql
   ```

2. **Manual restoration**:
   ```bash
   # PostgreSQL
   dropdb homeserver
   createdb homeserver
   psql homeserver < /var/backups/hotfix/snapshots/snapshot_id.sql
   
   # SQLite
   cp /var/backups/hotfix/snapshots/snapshot_id.db /path/to/database.db
   ```

### Service Recovery
Restore service states:

```bash
# Check service snapshots
python3 rollback_standalone.py --list-snapshots | grep service

# Restore service snapshot
python3 rollback_standalone.py --restore-snapshot <service_snapshot_id>
```

## 🔍 Troubleshooting

### Common Issues

#### Permission Errors
```bash
# Ensure proper ownership
chown -R www-data:www-data /var/www/homeserver/
chmod 755 /usr/local/lib/user_local_lib/updates/hotfix/src/*.sh
```

#### Backup Directory Issues
```bash
# Create backup directory
mkdir -p /var/backups/hotfix/snapshots
chown -R root:root /var/backups/hotfix
chmod 755 /var/backups/hotfix
```

#### Database Connection Issues
```bash
# Test database connectivity
pg_isready -h localhost -p 5432 -U postgres
```

### Debug Mode
Enable verbose logging:

```json
{
    "config": {
        "debug": true,
        "log_level": "DEBUG"
    }
}
```

## 📚 Examples

### Example 1: Security Patch
Fix a critical security vulnerability:

```json
{
    "metadata": {
        "schema_version": "1.1.0",
        "description": "Critical security patch for CVE-2024-XXXX"
    },
    "operations": [
        {
            "id": "patch_auth_bypass",
            "type": "copy",
            "source": "patched_auth.py",
            "target": "/var/www/homeserver/backend/auth.py",
            "backup": true,
            "enabled": true
        },
        {
            "id": "add_security_headers",
            "type": "append",
            "source": "security_headers.conf",
            "target": "/etc/nginx/sites-available/homeserver",
            "backup": true,
            "enabled": true
        },
        {
            "id": "restart_services",
            "type": "execute",
            "source": "restart_web_services.sh",
            "dependencies": ["patch_auth_bypass", "add_security_headers"],
            "enabled": true
        }
    ]
}
```

### Example 2: Database Migration
Handle a one-way database change:

```json
{
    "operations": [
        {
            "id": "capture_db_state",
            "type": "execute",
            "source": "capture_db_snapshot.sh",
            "phase": 1,
            "enabled": true
        },
        {
            "id": "migrate_schema",
            "type": "execute",
            "source": "migrate_database.sh",
            "phase": 2,
            "dependencies": ["capture_db_state"],
            "rollback_script": "rollback_migration.sh",
            "enabled": true
        },
        {
            "id": "validate_migration",
            "type": "execute",
            "source": "validate_schema.sh",
            "phase": 3,
            "dependencies": ["migrate_schema"],
            "enabled": true
        }
    ]
}
```

## 🔗 Related Documentation

- [Global Update System](../README.md)
- [Premium Tab Installer](../../premium/README.md)
- [HOMESERVER Configuration](../../../config/README.md)

## 📞 Support

For emergency support:
1. Check logs: `/var/log/homeserver/hotfix.log`
2. Use standalone rollback: `rollback_standalone.py`
3. Manual backup restoration from `/var/backups/hotfix/`
4. System snapshot locations in `/var/backups/hotfix/snapshots/`

Remember: The hotfix system is designed for **emergency situations**. Always test operations in a development environment when possible.
