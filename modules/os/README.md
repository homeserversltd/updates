# OS Update Module

Operating system update management system for HOMESERVER with safety checks and package manager integration.

## Overview

The OS module provides a controlled system for managing operating system updates through package managers (primarily apt). It implements safety checks and provides verification of update success.

## Design Philosophy

- **Safety First**: Implements maximum package limits
- **Verification Driven**: Comprehensive checks before and after updates
- **Configurable**: Flexible package manager configuration
- **Transparent**: Detailed logging and status reporting

## Architecture

### Update Flow

1. **Pre-Update Phase**:
   - Check for available updates
   - Verify package manager availability
   - Validate against safety limits

2. **Update Phase**:
   - Update package lists
   - Upgrade packages
   - Remove unused packages
   - Clean package cache

3. **Verification Phase**:
   - Check package manager availability
   - Verify no broken packages
   - Count remaining upgradable packages
   - Validate system state

## Configuration (index.json)

```json
{
    "metadata": {
        "schema_version": "1.0.0",
        "module_name": "os",
        "description": "Operating system update module",
        "enabled": true
    },
    "config": {
        "package_manager": {
            "type": "apt",
            "update_command": ["apt", "update"],
            "upgrade_command": ["apt", "upgrade", "-y"],
            "autoremove_command": ["apt", "autoremove", "-y"],
            "clean_command": ["apt", "clean"],
            "list_upgradable_command": ["apt", "list", "--upgradable"]
        },
        "safety": {
            "max_upgrade_count": 100,
            "skip_kernel_updates": false
        }
    }
}
```

### Configuration Properties

- **package_manager**: Package manager configuration
  - **type**: Package manager type (e.g., "apt")
  - **update_command**: Command to update package lists
  - **upgrade_command**: Command to upgrade packages
  - **autoremove_command**: Command to remove unused packages
  - **clean_command**: Command to clean package cache
  - **list_upgradable_command**: Command to list upgradable packages

- **safety**: Safety configuration
  - **max_upgrade_count**: Maximum number of packages to upgrade at once
  - **skip_kernel_updates**: Whether to skip kernel updates

## Usage

### Command Line Interface

The module supports several command-line modes:

```bash
# Check for available updates
python3 -m updates.modules.os --check

# Verify system state
python3 -m updates.modules.os --verify

# Show current configuration
python3 -m updates.modules.os --config

# Run update (no arguments)
python3 -m updates.modules.os
```

### Return Values

The module returns a dictionary with the following structure:

```python
{
    "success": bool,           # Overall success status
    "updated": bool,          # Whether updates were performed
    "upgradable": int,        # Number of upgradable packages
    "verification": dict,     # Verification results
    "config": dict,          # Current configuration
    "error": str             # Error message (if any)
}
```

## Safety Features

### Package Limits

- Maximum number of packages that can be upgraded at once
- Prevents accidental mass updates
- Configurable through `max_upgrade_count`

### Verification Checks

- Package manager availability
- No broken packages
- Remaining upgradable packages
- System state validation

## Integration with Broader System

### Logging System

- Detailed operation logging
- Error tracking and reporting
- Status updates during operations

## Best Practices

### Configuration

- Set appropriate `max_upgrade_count` for your environment
- Adjust package manager commands for your distribution

### Safety

- Monitor `max_upgrade_count` for your update patterns
- Review verification results after updates
- Consider system impact before large updates

### Maintenance

- Regular verification runs to check system state

## Development Workflow

### Adding New Features

1. Update configuration schema in `index.json`
2. Implement new functionality in `index.py`
3. Add appropriate verification steps
4. Update documentation

### Testing Updates

- Test with small package sets first
- Verify all verification steps
- Validate logging output

## Error Handling

### Common Scenarios

- **Package Manager Unavailable**: Logs error and returns failure
- **Too Many Updates**: Aborts before starting update
- **Update Failure**: Logs error and reports status
- **Verification Failure**: Logs details and returns failure

### Recovery Procedures

1. Check logs for specific error
2. Verify system state
3. Review and adjust safety limits

## Migration from Legacy System

The new OS module replaces the previous update system with:

- Structured configuration
- Comprehensive verification
- Safety limits

Benefits:
- More reliable updates
- Better error handling
- Improved safety features
- Consistent with other modules 