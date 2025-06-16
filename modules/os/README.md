# OS Update Module

Operating system update management system for HOMESERVER with safety checks, package manager integration, and intelligent batch processing.

## Overview

The OS module provides a controlled system for managing operating system updates through package managers (primarily apt). It implements safety checks, batch processing for large package sets, and provides verification of update success.

## Design Philosophy

- **Safety First**: Implements maximum package limits with intelligent batch processing
- **Scalability**: Handles large numbers of packages through automated batching
- **Verification Driven**: Comprehensive checks before and after updates
- **Configurable**: Flexible package manager configuration
- **Transparent**: Detailed logging and status reporting

## Architecture

### Update Flow

1. **Pre-Update Phase**:
   - Check for available updates
   - Verify package manager availability
   - Get complete list of upgradable packages

2. **Update Phase**:
   - Update package lists
   - **Batch Processing**: If packages exceed threshold, process in batches
   - Upgrade packages (in batches if needed)
   - Remove unused packages
   - Clean package cache

3. **Verification Phase**:
   - Check package manager availability
   - Verify no broken packages
   - Count remaining upgradable packages
   - Validate system state

## Batch Processing

When the number of upgradable packages exceeds the configured `max_upgrade_count`, the module automatically:

1. **Splits packages into batches** of the maximum allowed size
2. **Processes each batch sequentially** to maintain system stability
3. **Updates package lists between batches** to get current state
4. **Tracks progress** with detailed logging
5. **Handles failures gracefully** by stopping at failed batches

### Benefits of Batch Processing

- **System Stability**: Prevents overwhelming the system with too many simultaneous updates
- **Progress Tracking**: Clear visibility into which batches succeed or fail
- **Failure Isolation**: Failed batches don't prevent other batches from processing
- **Resource Management**: Controlled memory and CPU usage during large updates

## Configuration (index.json)

```json
{
    "metadata": {
        "schema_version": "1.0.4",
        "module_name": "os",
        "description": "Operating system update module",
        "enabled": true
    },
    "config": {
        "package_manager": {
            "update_command": ["apt", "update"],
            "upgrade_command": ["apt", "upgrade", "-y"],
            "autoremove_command": ["apt", "autoremove", "-y"],
            "clean_command": ["apt", "autoclean"],
            "list_upgradable_command": ["apt", "list", "--upgradable"]
        },
        "safety": {
            "max_upgrade_count": 100
        }
    }
}
```

### Configuration Properties

- **package_manager**: Package manager configuration
  - **update_command**: Command to update package lists
  - **upgrade_command**: Command to upgrade packages
  - **autoremove_command**: Command to remove unused packages
  - **clean_command**: Command to clean package cache
  - **list_upgradable_command**: Command to list upgradable packages

- **safety**: Safety configuration
  - **max_upgrade_count**: Maximum number of packages to upgrade per batch

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

# Run update with batch processing (no arguments)
python3 -m updates.modules.os
```

### Return Values

The module returns a dictionary with the following structure:

```python
{
    "success": bool,           # Overall success status
    "updated": bool,          # Whether updates were performed
    "upgradable": int,        # Number of upgradable packages initially
    "upgradable_after": int,  # Number of upgradable packages after update
    "batches_processed": int, # Number of batches successfully processed
    "total_upgraded": int,    # Total number of packages upgraded
    "verification": dict,     # Verification results
    "config": dict,          # Current configuration
    "error": str             # Error message (if any)
}
```

## Batch Processing Examples

### Small Package Set (≤ 100 packages)
```
[INFO] Found 45 upgradable packages
[INFO] Upgrading 45 packages...
[INFO] All packages upgraded successfully
```

### Large Package Set (> 100 packages)
```
[INFO] Found 288 upgradable packages
[INFO] Large number of packages (288) detected. Processing in batches of 100
[INFO] Processing batch 1: 100 packages
[INFO] Batch 1 completed successfully
[INFO] Updating package lists between batches...
[INFO] Processing batch 2: 100 packages
[INFO] Batch 2 completed successfully
[INFO] Processing batch 3: 88 packages
[INFO] Batch 3 completed successfully
[INFO] All packages upgraded successfully
```

## Safety Features

### Intelligent Batch Processing

- Automatically splits large package sets into manageable batches
- Configurable batch size through `max_upgrade_count`
- Progress tracking and failure isolation
- Dynamic package list refresh between batches

### Verification Checks

- Package manager availability
- No broken packages
- Remaining upgradable packages
- System state validation

## Integration with Broader System

### Logging System

- Detailed operation logging with batch progress
- Error tracking and reporting
- Status updates during batch operations

### StateManager Integration

- Compatible with HOMESERVER backup and restore systems
- Maintains system state consistency during batch operations

## Best Practices

### Configuration

- Set appropriate `max_upgrade_count` for your system resources
- Consider system memory and CPU when setting batch sizes
- Adjust package manager commands for your distribution

### Safety

- Monitor batch processing logs for any failures
- Review verification results after large batch operations
- Consider system load during batch processing

### Maintenance

- Regular verification runs to check system state
- Monitor batch processing performance over time

## Development Workflow

### Adding New Features

1. Update configuration schema in `index.json`
2. Implement new functionality in `index.py`
3. Add appropriate verification steps
4. Update documentation
5. Increment schema version

### Testing Updates

- Test with both small and large package sets
- Verify batch processing logic
- Validate all verification steps
- Test failure scenarios and recovery

## Error Handling

### Common Scenarios

- **Package Manager Unavailable**: Logs error and returns failure
- **Batch Processing Failure**: Stops at failed batch, reports progress
- **Update Failure**: Logs error and reports status
- **Verification Failure**: Logs details and returns failure

### Recovery Procedures

1. Check logs for specific batch or package errors
2. Verify system state after partial completion
3. Review and adjust batch size if needed
4. Re-run update to continue from where it stopped

## Migration from Legacy System

The enhanced OS module replaces the previous update system with:

- Intelligent batch processing for large package sets
- Structured configuration
- Comprehensive verification
- Better progress tracking

Benefits:
- Handles large package sets automatically
- More reliable updates through batching
- Better error handling and recovery
- Improved safety features
- Consistent with other HOMESERVER modules 