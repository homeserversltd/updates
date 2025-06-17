# Linker Update Module

Git-based updater for HOMESERVER linker script suite with StateManager integration.

## Overview

The linker module handles updating the HOMESERVER linker script suite from the GitHub repository. It supports component-based updates, automatic rollback on failure, and comprehensive script management.

## Design Philosophy

- **Component-based updates**: Update scripts and configuration independently
- **GitHub integration**: Shallow cloning for efficient repository access
- **StateManager integration**: Reliable backup and restore of all components
- **Simple update process**: Direct file replacement with permission preservation
- **Customer-first approach**: Failed updates don't break existing installations

## Architecture

### Component Structure

The module manages two distinct components:
- **Scripts**: Executable linker scripts
- **Config**: Configuration files

### Update Flow

1. **Backup Phase**
   - StateManager backs up all enabled components
   - Backup location: `/var/backups/linker`

2. **Repository Phase**
   - Shallow clone of GitHub repository
   - Temporary directory: `/tmp/homeserver-linker-update`
   - Branch selection via configuration

3. **Component Update Phase**
   - Update each enabled component
   - Remove existing target before copy
   - Preserve file permissions
   - Skip disabled components

4. **Rollback Phase** (on failure)
   - Restore all components via StateManager
   - Clean up temporary directory

## Configuration (index.json)

```json
{
    "metadata": {
        "schema_version": "1.0.0",
        "module_name": "linker",
        "description": "HOMESERVER linker script suite update system via GitHub",
        "enabled": true
    },
    "config": {
        "repository": {
            "url": "https://github.com/homeserversltd/linker.git",
            "branch": "master",
            "temp_directory": "/tmp/homeserver-linker-update"
        },
        "target_paths": {
            "base_directory": "/usr/local/bin",
            "components": {
                "scripts": {
                    "enabled": true,
                    "source_path": "scripts",
                    "target_path": "/usr/local/bin",
                    "description": "Linker script suite executables"
                },
                "config": {
                    "enabled": true,
                    "source_path": "config",
                    "target_path": "/etc/homeserver/linker",
                    "description": "Linker configuration files"
                }
            }
        }
    }
}
```

### Configuration Options

- **repository**: GitHub repository settings
  - **url**: Repository URL
  - **branch**: Target branch
  - **temp_directory**: Temporary clone location

- **target_paths**: Component configuration
  - **base_directory**: Root installation directory
  - **components**: Individual component settings
    - **enabled**: Whether to update this component
    - **source_path**: Path in repository
    - **target_path**: Installation path
    - **description**: Component purpose

## Component Management

### Script Updates
- Executable linker scripts
- Preserves file permissions
- Direct file replacement

### Config Updates
- Configuration files
- Preserves file permissions
- Direct file replacement

## Error Handling

### Graceful Degradation
- Failed components don't affect others
- Temporary files are cleaned up
- Rollback preserves functionality

### Error Categories
1. **Backup Errors**
   - StateManager backup failure
   - Insufficient permissions
   - Disk space issues

2. **Repository Errors**
   - Clone failures
   - Network issues
   - Invalid repository

3. **Component Errors**
   - File copy failures
   - Permission issues
   - Missing source files

## Command Line Interface

### Check Status
```bash
python3 index.py --check
```
Returns:
- Enabled components
- Total components
- Schema version

### Version Check
```bash
python3 index.py --version
```
Returns:
- Schema version
- Module name

### Full Update
```bash
python3 index.py
```
Performs complete update process with:
- Component updates
- Validation

## Integration Points

### Orchestrator Interface
- **Entry Point**: `main(args=None)` function
- **Return Value**: Dictionary with success status and details
- **Logging**: Uses standard update logging system

### StateManager Integration
- Uses standard backup/restore patterns
- Consistent with other module rollback strategies
- No special rollback machinery needed

## Best Practices

### Component Updates
- Keep components focused and independent
- Use descriptive component names
- Document component purposes
- Enable/disable as needed

### Error Handling
- Log detailed error messages
- Clean up on all exit paths
- Use StateManager for rollback

## Development Workflow

### Adding Components
1. Add component to `index.json`
2. Set appropriate paths
3. Enable/disable as needed
4. Test update process

### Testing Updates
- Test each component independently
- Verify file permissions
- Validate rollback

### Schema Updates
- Increment schema version
- Update component configurations
- Test with existing installations
- Document changes 