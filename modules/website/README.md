# Website Update Module

Git-based website updater for HOMESERVER with component-based updates and StateManager integration.

## Overview

The website module handles updating the HOMESERVER web interface from the GitHub repository. It supports selective component updates, automatic rollback on failure, and comprehensive build process management.

## Design Philosophy

- **Component-based updates**: Update frontend, backend, premium features, and public assets independently
- **GitHub integration**: Shallow cloning for efficient repository access
- **StateManager integration**: Reliable backup and restore of all components
- **Build process management**: npm install, build, and service restarts with validation
- **Customer-first approach**: Failed updates don't break existing installations

## Architecture

### Component Structure

The module manages five distinct components:
- **Frontend**: React components and assets
- **Backend**: Flask backend API and services
- **Premium**: Premium features and functionality
- **Public**: Static public assets
- **Config**: NPM package configuration

### Update Flow

1. **Backup Phase**
   - StateManager backs up all enabled components
   - Includes package-lock.json if present
   - Backup location: `/var/backups/website`

2. **Repository Phase**
   - Shallow clone of GitHub repository
   - Temporary directory: `/tmp/homeserver-website-update`
   - Branch selection via configuration

3. **Component Update Phase**
   - Update each enabled component
   - Remove existing target before copy
   - Preserve directory structure
   - Skip disabled components

4. **Build Phase**
   - Stop homeserver service
   - Run npm install (600s timeout)
   - Run npm build (600s timeout)
   - Start homeserver service
   - Validate service is active
   - Restart gunicorn service
   - Validate gunicorn is active

5. **Rollback Phase** (on failure)
   - Restore all components via StateManager
   - Restart services after rollback
   - Clean up temporary directory

## Configuration (index.json)

```json
{
    "metadata": {
        "schema_version": "1.0.0",
        "module_name": "website",
        "description": "HOMESERVER website frontend/backend update system via GitHub",
        "enabled": true
    },
    "config": {
        "repository": {
            "url": "https://github.com/homeserversltd/website.git",
            "branch": "master",
            "temp_directory": "/tmp/homeserver-website-update"
        },
        "target_paths": {
            "base_directory": "/var/www/homeserver",
            "components": {
                "frontend": {
                    "enabled": true,
                    "source_path": "src",
                    "target_path": "/var/www/homeserver/src",
                    "description": "React frontend components and assets"
                },
                "backend": {
                    "enabled": true,
                    "source_path": "backend",
                    "target_path": "/var/www/homeserver/backend",
                    "description": "Flask backend API and services"
                },
                "premium": {
                    "enabled": true,
                    "source_path": "premium",
                    "target_path": "/var/www/homeserver/premium",
                    "description": "Premium features and functionality"
                },
                "public": {
                    "enabled": true,
                    "source_path": "public",
                    "target_path": "/var/www/homeserver/public",
                    "description": "Static public assets"
                },
                "config": {
                    "enabled": true,
                    "source_path": "package.json",
                    "target_path": "/var/www/homeserver/package.json",
                    "description": "NPM package configuration"
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

### Frontend Updates
- React components and assets
- Requires npm build process
- Service restart validation

### Backend Updates
- Flask API and services
- Gunicorn service management
- Active status validation

### Premium Features
- Premium functionality
- Independent of core updates
- Can be disabled if not licensed

### Public Assets
- Static files and resources
- No build process required
- Direct file replacement

### Config Updates
- package.json management
- Triggers npm install
- Preserves package-lock.json

## Build Process

### Service Management
1. Stop homeserver service
2. Run npm install (600s timeout)
3. Run npm build (600s timeout)
4. Start homeserver service
5. Validate service is active
6. Restart gunicorn service
7. Validate gunicorn is active

### Timeouts
- npm install: 600 seconds
- npm build: 600 seconds
- Service operations: 300 seconds

### Validation
- Service active checks after restarts
- Build process success verification
- Component update confirmation

## Rollback Strategy

### StateManager Integration
- Backup location: `/var/backups/website`
- Backup scope: All enabled components
- Restore trigger: Any update/build failure
- Service restart after rollback

### Rollback Triggers
- Repository clone failure
- Component update failure
- Build process failure
- Service restart failure
- Unexpected errors

## Error Handling

### Graceful Degradation
- Failed components don't affect others
- Service restarts are validated
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

4. **Build Errors**
   - npm install failures
   - Build process errors
   - Service restart issues

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
- Build process
- Service restarts
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

### Service Management
- systemctl for service control
- Active status validation
- Graceful stop/start sequence

## Best Practices

### Component Updates
- Keep components focused and independent
- Use descriptive component names
- Document component purposes
- Enable/disable as needed

### Build Process
- Validate service status after restarts
- Use appropriate timeouts
- Clean up temporary files
- Preserve package-lock.json

### Error Handling
- Log detailed error messages
- Clean up on all exit paths
- Validate service status
- Use StateManager for rollback

## Development Workflow

### Adding Components
1. Add component to `index.json`
2. Set appropriate paths
3. Enable/disable as needed
4. Test update process

### Testing Updates
- Test each component independently
- Verify build process
- Check service restarts
- Validate rollback

### Schema Updates
- Increment schema version
- Update component configurations
- Test with existing installations
- Document changes
