# Filebrowser Update Module

> **Enhanced with StateManager Integration and Configuration Management**

## Overview

The Filebrowser update module provides comprehensive management of the Filebrowser web interface with advanced backup and state management capabilities. All paths and settings are configurable through `index.json`.

## Configuration

### index.json Structure

```json
{
    "metadata": {
        "schema_version": "1.0.0",
        "module_name": "filebrowser",
        "description": "File browser web interface",
        "enabled": true
    },
    "config": {
        "directories": {
            "data_dir": "/var/lib/filebrowser",
            "config_dir": "/etc/filebrowser"
        },
        "installation": {
            "github_api_url": "https://api.github.com/repos/filebrowser/filebrowser/releases/latest"
        }
    }
}
```

### Configuration Sections

#### `directories`
- **data_dir**: Main Filebrowser data directory (`/var/lib/filebrowser`)
- **config_dir**: Filebrowser configuration directory (`/etc/filebrowser`)

#### `installation`
- **github_api_url**: GitHub API URL for version checking

## Usage

### Command Line Interface

```bash
# Check current version
python3 -m updates.modules.filebrowser --version

# Comprehensive verification
python3 -m updates.modules.filebrowser --verify

# Show configuration
python3 -m updates.modules.filebrowser --config

# Run update (with automatic backup/restore)
python3 -m updates.modules.filebrowser
```

### Programmatic Interface

```python
from updates.modules.filebrowser import (
    main,
    get_filebrowser_version,
    get_latest_filebrowser_version,
    verify_filebrowser_installation
)

# Run update with full state management
result = main()
print(f"Update success: {result['success']}")

# Check versions
current = get_filebrowser_version()
latest = get_latest_filebrowser_version()
print(f"Current: {current}, Latest: {latest}")

# Verify installation
verification = verify_filebrowser_installation()
if verification["binary_executable"]:
    print("Filebrowser is properly installed")
```

### StateManager Integration

The module uses StateManager for atomic backup and restore operations during updates:

```python
from updates.utils.state_manager import StateManager

# StateManager is automatically used during updates
result = main()
if not result["success"] and result.get("rollback_success"):
    print("Update failed but state was successfully restored")
```

## Update Process Flow

### 1. Pre-Update Phase
- Load configuration from `index.json`
- Verify paths and permissions
- Check current vs. latest version
- Create comprehensive state backup using StateManager

### 2. Update Phase
- Download and install new version using official installation script
- Verify installation integrity
- Check version consistency

### 3. Post-Update Phase
- Run comprehensive verification
- Return detailed results

### 4. State Restoration on Failure
- Automatic state restoration on any failure
- Restore all backed up files and directories
- Verify restoration success
- Log detailed error information

## Backup Strategy

### What Gets Backed Up
- **Data Directory**: Complete `/var/lib/filebrowser` directory
- **Configuration Directory**: All config files in `/etc/filebrowser`

### Backup Features
- **Atomic Operations**: All-or-nothing backup creation
- **Checksum Verification**: SHA-256 checksums for integrity
- **Metadata Tracking**: Timestamps, descriptions, module info

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
from updates.modules.filebrowser import main

result = main()
if result["success"]:
    if result.get("updated"):
        print(f"Filebrowser updated: {result['old_version']} → {result['new_version']}")
    else:
        print(f"Filebrowser already current: {result['version']}")
else:
    print(f"Filebrowser update failed: {result['error']}")
    if result.get("rollback_success"):
        print("Successfully restored to previous state")
```

## Configuration Management

### Validation
```python
# Configuration is validated during module initialization
from updates.modules.filebrowser import main

# Run with --config to validate and show current configuration
result = main(["--config"])
if result["success"]:
    print("Configuration is valid")
```

## Best Practices

### Configuration Management
1. **Version Control**: Keep `index.json` in version control
2. **Environment-Specific**: Use different configs for dev/prod
3. **Validation**: Always validate config after changes
4. **Documentation**: Document any custom path changes

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
python3 -c "import json; print(json.load(open('index.json')))"

# Validate configuration
python3 -m updates.modules.filebrowser --config
```

#### Update Failures
```bash
# Run verification to check installation
python3 -m updates.modules.filebrowser --verify

# Check logs for detailed error information
journalctl -u filebrowser
```

### Debug Mode
Set environment variable for detailed logging:
```bash
export FILEBROWSER_UPDATE_DEBUG=1
python3 -m updates.modules.filebrowser
```

## Security Considerations

### File Permissions
- Backup directory should be writable by update process
- Filebrowser directories should maintain proper ownership
- Configuration files should not be world-readable

### Network Security
- Installation script downloaded over HTTPS
- GitHub API accessed over HTTPS
- Consider using local mirrors for air-gapped environments

### Backup Security
- Backups contain configuration and data
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