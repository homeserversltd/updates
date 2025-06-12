# Gogs Update Module

> **Enhanced with StateManager Integration and Configuration Management**

## Overview

The Gogs update module provides comprehensive management of the Gogs Git server with advanced backup and state management capabilities. All paths and settings are configurable through `index.json`.

## Configuration

### index.json Structure

```json
{
    "metadata": {
        "schema_version": "1.0.0",
        "module_name": "gogs",
        "description": "Self-hosted Git service",
        "enabled": true
    },
    "config": {
        "directories": {
            "data_dir": "/var/lib/gogs",
            "config_dir": "/etc/gogs",
            "install_dir": "/opt/gogs",
            "config_file": "/opt/gogs/custom/conf/app.ini",
            "repo_path": "/mnt/nas/git/repositories",
            "gogs_bin": "/opt/gogs/gogs"
        },
        "installation": {
            "github_api_url": "https://api.github.com/repos/gogs/gogs/releases/latest",
            "download_url_template": "https://dl.gogs.io/{version}/gogs_{version}_linux_amd64.tar.gz",
            "extract_path": "/opt/"
        },
        "permissions": {
            "owner": "git",
            "group": "git",
            "mode": "750"
        }
    }
}
```

### Configuration Sections

#### `directories`
- **data_dir**: Main Gogs data directory
- **config_dir**: Gogs configuration directory
- **install_dir**: Gogs installation directory
- **config_file**: Main configuration file path
- **repo_path**: Git repositories storage location
- **gogs_bin**: Gogs binary location

#### `installation`
- **github_api_url**: GitHub API URL for version checking
- **download_url_template**: Template for downloading Gogs releases
- **extract_path**: Base path for extracting Gogs installation

#### `permissions`
- **owner**: File ownership user
- **group**: File ownership group
- **mode**: File permissions in octal

## Usage

### Command Line Interface

```bash
# Check current version
python3 -m updates.modules.gogs --version

# Comprehensive verification
python3 -m updates.modules.gogs --verify

# Show configuration
python3 -m updates.modules.gogs --config

# Run update (with automatic backup/restore)
python3 -m updates.modules.gogs
```

### Programmatic Interface

```python
from updates.modules.gogs import (
    main,
    get_gogs_version,
    get_latest_gogs_version,
    verify_gogs_installation
)

# Run update with full state management
result = main()
print(f"Update success: {result['success']}")

# Check versions
current = get_gogs_version()
latest = get_latest_gogs_version()
print(f"Current: {current}, Latest: {latest}")

# Verify installation
verification = verify_gogs_installation()
if verification["binary_executable"]:
    print("Gogs is properly installed")
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
- Download and extract new version
- Set proper permissions
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
- **Data Directory**: Complete Gogs data directory
- **Configuration Directory**: All config files
- **Installation Directory**: Gogs installation
- **Repository Directory**: Git repositories

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
from updates.modules.gogs import main

result = main()
if result["success"]:
    if result.get("updated"):
        print(f"Gogs updated: {result['old_version']} → {result['new_version']}")
    else:
        print(f"Gogs already current: {result['version']}")
else:
    print(f"Gogs update failed: {result['error']}")
    if result.get("rollback_success"):
        print("Successfully restored to previous state")
```

## Configuration Management

### Validation
```python
from updates.modules.gogs import main

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
python3 -m updates.modules.gogs --config
```

#### Update Failures
```bash
# Run verification to check installation
python3 -m updates.modules.gogs --verify

# Check logs for detailed error information
journalctl -u gogs
```

### Debug Mode
Set environment variable for detailed logging:
```bash
export GOGS_UPDATE_DEBUG=1
python3 -m updates.modules.gogs
```

## Security Considerations

### File Permissions
- Backup directory should be writable by update process
- Gogs directories should maintain proper ownership
- Configuration files should not be world-readable

### Network Security
- Installation files downloaded over HTTPS
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