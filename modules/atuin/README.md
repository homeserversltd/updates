# Atuin Update Module

> **Enhanced with StateManager Integration and Configuration Management**

## Overview

The Atuin update module provides comprehensive management of the Atuin shell history tool with advanced backup and state management capabilities. All paths and settings are configurable through `index.json`.

## Configuration

### index.json Structure

```json
{
    "metadata": {
        "schema_version": "1.0.0",
        "module_name": "atuin",
        "description": "Atuin shell history management tool"
    },
    "config": {
        "admin_user_uid": 1000,
        "directories": {
            "atuin_root": "/home/{admin_user}/.atuin",
            "atuin_bin": "/home/{admin_user}/.atuin/bin/atuin",
            "atuin_env": "/home/{admin_user}/.atuin/bin/env",
            "config_dir": "/home/{admin_user}/.config/atuin",
            "data_dir": "/home/{admin_user}/.local/share/atuin"
        },
        "backup": {
            "backup_dir": "/var/backups/updates",
            "include_paths": [
                "{atuin_root}",
                "{config_dir}",
                "{data_dir}"
            ]
        },
        "installation": {
            "install_script_url": "https://setup.atuin.sh",
            "github_api_url": "https://api.github.com/repos/atuinsh/atuin/releases/latest"
        }
    }
}
```

### Configuration Sections

#### `directories`
- **atuin_root**: Main Atuin installation directory
- **atuin_bin**: Path to Atuin binary
- **atuin_env**: Path to Atuin environment file
- **config_dir**: User configuration directory
- **data_dir**: User data directory

#### `backup`
- **backup_dir**: Global backup storage location
- **include_paths**: Paths to include in backups (supports templates)

#### `installation`
- **install_script_url**: URL for Atuin installation script
- **github_api_url**: GitHub API URL for version checking

## Usage

### Command Line Interface

```bash
# Check current version
python -m updates.modules.atuin --check

# Comprehensive verification
python -m updates.modules.atuin --verify

# Show configuration
python -m updates.modules.atuin --config

# Run update (with automatic backup/restore)
python -m updates.modules.atuin
```

### Programmatic Interface

```python
from updates.modules.atuin import (
    main, 
    create_atuin_backup,
    restore_atuin_backup,
    list_atuin_backups,
    cleanup_atuin_backups,
    get_atuin_config,
    validate_atuin_config
)

# Run update with full state management
result = main()
print(f"Update success: {result['success']}")

# Create manual backup
backup_result = create_atuin_backup("pre_maintenance")
if backup_result["success"]:
    backup_info = backup_result["backup_info"]
    print(f"Backup created: {backup_info}")

# List available backups
backups = list_atuin_backups()
for backup in backups:
    print(f"Backup: {backup}")

# Validate configuration
validation = validate_atuin_config()
if not validation["valid"]:
    print("Configuration errors:", validation["errors"])
```

### StateManager Integration

```python
from updates.utils.state_manager import StateManager
from updates.modules.atuin import get_backup_config

# Use Atuin's configured backup directory
backup_config = get_backup_config()
state_manager = StateManager(backup_config["backup_dir"])

# List all Atuin backups
atuin_backups = state_manager.get_backup_info(module_name="atuin")

# Restore module state
success = state_manager.restore_module_state(module_name="atuin")
```

## Update Process Flow

### 1. Pre-Update Phase
- Load configuration from `index.json`
- Verify admin user and paths
- Check current vs. latest version
- Create comprehensive state backup

### 2. Update Phase
- Download and install new version using configured URL
- Verify installation integrity
- Check version consistency

### 3. Post-Update Phase
- Run comprehensive verification
- Clean up old backups per retention policy
- Return detailed results

### 4. State Restoration on Failure
- Automatic state restoration on any failure
- Restore all backed up files and directories
- Verify restoration success
- Log detailed error information

## Backup Strategy

### What Gets Backed Up
- **Atuin Root Directory**: Complete `.atuin` directory
- **Configuration Directory**: User config files
- **Data Directory**: History database and user data
- **Additional Paths**: Any paths specified in `include_paths`

### Backup Features
- **Atomic Operations**: All-or-nothing backup creation
- **Checksum Verification**: SHA-256 checksums for integrity
- **Metadata Tracking**: Timestamps, descriptions, module info
- **Retention Policies**: Automatic cleanup of old backups
- **Path Templates**: Dynamic path resolution with user substitution

## Error Handling

### Graceful Degradation
- Configuration loading failures fall back to defaults
- Missing paths are logged but don't stop the process
- Partial backup failures are logged with warnings

### Comprehensive Logging
- All operations logged with appropriate levels
- Detailed error messages with context
- Verification results with pass/fail status

### State Restoration Guarantees
- Failed updates trigger automatic state restoration
- Restoration success is verified and reported
- Original state restoration is confirmed

## Integration Examples

### With Update Orchestrator

```python
# In update orchestrator
from updates.modules.atuin import main

result = main()
if result["success"]:
    if result.get("updated"):
        print(f"Atuin updated: {result['old_version']} → {result['new_version']}")
    else:
        print(f"Atuin already current: {result['version']}")
else:
    print(f"Atuin update failed: {result['error']}")
    if result.get("rollback_success"):
        print("Successfully restored to previous state")
```

### With Custom Backup Scripts

```python
# Create backup before maintenance
backup_result = create_atuin_backup("pre_maintenance_2024")
backup_info = backup_result["backup_info"]

# Perform maintenance operations...

# Restore if needed
if maintenance_failed:
    restore_result = restore_atuin_backup()
    if restore_result["success"]:
        print("Successfully restored from backup")
```

## Configuration Management

### Validation
```python
validation = validate_atuin_config()
if validation["valid"]:
    print("Configuration is valid")
else:
    print("Errors:", validation["errors"])
    print("Warnings:", validation["warnings"])
```

### Runtime Reloading
```python
# Reload configuration after changes
new_config = reload_atuin_config()
print(f"Reloaded config version: {new_config['metadata']['schema_version']}")
```

### Path Resolution
```python
# Get resolved paths for current admin user
config = get_atuin_config()
admin_user = get_admin_user()

for key, template in config["config"]["directories"].items():
    resolved_path = template.format(admin_user=admin_user)
    print(f"{key}: {resolved_path}")
```

## Best Practices

### Configuration Management
1. **Version Control**: Keep `index.json` in version control
2. **Environment-Specific**: Use different configs for dev/prod
3. **Validation**: Always validate config after changes
4. **Documentation**: Document any custom path changes

### State Management
1. **Regular Cleanup**: Run cleanup periodically to manage disk space
2. **Monitoring**: Monitor backup success/failure rates
3. **Testing**: Periodically test restore procedures
4. **Retention**: Adjust retention policies based on usage patterns

### Update Safety
1. **Pre-Update Backups**: Always create backups before updates
2. **Verification**: Run verification after updates
3. **Restore Testing**: Test restore procedures in non-production
4. **Monitoring**: Monitor update success rates and failure patterns

## Troubleshooting

### Common Issues

#### Configuration Not Loading
```bash
# Check config file exists and is valid JSON
python -c "import json; print(json.load(open('index.json')))"

# Validate configuration
python -m updates.modules.atuin --config
```

#### Backup Failures
```bash
# Check backup directory permissions
ls -la /var/backups/updates

# Check disk space
df -h /var/backups

# List existing backups
python -c "from updates.modules.atuin import list_atuin_backups; print(list_atuin_backups())"
```

#### Update Failures
```bash
# Run verification to check installation
python -m updates.modules.atuin --verify

# Check logs for detailed error information
journalctl -u your-service-name
```

### Debug Mode
Set environment variable for detailed logging:
```bash
export ATUIN_UPDATE_DEBUG=1
python -m updates.modules.atuin
```

## Security Considerations

### File Permissions
- Backup directory should be writable by update process
- Atuin directories should maintain proper user ownership
- Configuration files should not be world-readable

### Network Security
- Installation script downloaded over HTTPS
- GitHub API accessed over HTTPS
- Consider using local mirrors for air-gapped environments

### Backup Security
- Backups contain user history data
- Consider encryption for sensitive environments
- Implement proper access controls on backup directory

## Future Enhancements

### Planned Features
- [ ] Encrypted backup support
- [ ] Remote backup destinations
- [ ] Incremental backup support
- [ ] Configuration schema validation
- [ ] Integration with system package managers
- [ ] Automated state restoration triggers based on health checks

### Extension Points
- Custom backup destinations via configuration
- Plugin system for additional verification checks
- Integration with external monitoring systems
- Custom state restoration triggers and conditions 