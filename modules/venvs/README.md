# HOMESERVER Virtual Environment Management

## Overview
The Virtual Environment Management module provides enterprise-grade Python virtual environment orchestration for HOMESERVER services. This module ensures consistent, isolated Python environments across the platform while maintaining strict version control and dependency management.

## Key Features
- Automated virtual environment creation and maintenance
- Version-pinned package management
- Comprehensive verification and health checks
- Enterprise-grade rollback capabilities
- System-wide virtual environment orchestration

## Managed Environments

### Flask Backend (`/var/www/homeserver/venv`)
Core web interface backend with pinned dependencies:
- Flask 3.1.0
- Eventlet 0.39.0
- Gunicorn 23.0.0
- Cryptography 44.0.3
- Flask-CORS 5.0.0
- Flask-SocketIO 5.5.1
- Additional system utilities

### Linker Utility (`/usr/local/lib/linker/venv`)
System management interface with:
- Rich terminal interface
- Textual TUI framework

### Update System (`/usr/local/lib/updates/venv`)
Core update management with:
- Requests 2.28.0+
- Pathlib2 2.3.0+ (Python < 3.4)

## Usage

### Command Line Interface
```bash
# Show current configuration
python3 -m updates.modules.venvs --config

# Verify all environments
python3 -m updates.modules.venvs --verify

# Check environment existence
python3 -m updates.modules.venvs --check

# Perform full update
python3 -m updates.modules.venvs
```

### Verification Process
The module performs comprehensive verification:
- Environment existence validation
- Activation script verification
- Package availability checks
- Dependency verification
- Health status reporting

### Rollback System
- Automatic pre-update backups
- Configurable retention policies
- Point-in-time restoration
- Backup cleanup management

## Configuration

### Source-Based Requirements Management
Package requirements are managed through individual files in the `src/` directory:
- `src/flask.txt` - Flask backend requirements
- `src/linker.txt` - Linker utility requirements  
- `src/updater.txt` - Update system requirements

### Environment Configuration
Environment configurations are managed through `index.json`:
```json
{
    "virtual_environments": {
        "environment_name": {
            "path": "/path/to/venv",
            "requirements_source": "environment.txt",
            "upgrade_pip": true,
            "system_packages": false,
            "description": "Purpose description"
        }
    }
}
```

### Version Management
To update package versions:
1. Edit the appropriate requirements file in `src/`
2. Bump the `schema_version` in `index.json` metadata
3. Deploy via normal update mechanism

This approach enables:
- Individual package version control
- Systematic version bumps across environments
- Clear separation of concerns
- Easy maintenance and auditing

## Technical Requirements
- Python 3.4+
- System-level access for environment creation
- Sufficient disk space for environments and backups
- Network access for package installation

## Security Considerations
- Virtual environments are isolated by default
- System packages are disabled by default
- Package versions are explicitly pinned
- Activation scripts are verified
- Backup data is protected

## Troubleshooting
1. **Environment Creation Fails**
   - Verify system Python installation
   - Check disk space availability
   - Confirm directory permissions

2. **Package Installation Issues**
   - Verify network connectivity
   - Check package version compatibility
   - Review pip installation logs

3. **Verification Failures**
   - Run `--verify` for detailed diagnostics
   - Check activation script permissions
   - Verify Python interpreter availability

## License
This module is part of HOMESERVER and is licensed under the GNU General Public License v3.0.

## Support
For issues and feature requests, please use the HOMESERVER issue tracker. Include:
- Environment configuration
- Verification output
- Relevant error messages
- System information 