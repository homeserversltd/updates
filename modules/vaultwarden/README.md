# Vaultwarden Update Module

## Overview

The Vaultwarden update module provides automated update management for the Vaultwarden password manager service within the HOMESERVER ecosystem. This module handles binary updates, web vault updates, service management, and comprehensive backup/rollback functionality.

## Features

- **Automated Updates**: Fetches latest releases from GitHub and performs complete updates
- **Dual Component Management**: Updates both the Vaultwarden binary and web vault interface
- **Comprehensive Backup**: Creates rollback points before updates with full system state preservation
- **Service Integration**: Manages systemd service lifecycle during updates
- **Verification System**: Post-update validation ensures successful deployment
- **Configuration Management**: JSON-based configuration with sensible defaults

## Architecture

### Core Components

- **`index.py`**: Main update logic and orchestration
- **`index.json`**: Module configuration and metadata
- **`__init__.py`**: Package initialization and entry point exposure

### Update Process Flow

1. **Version Detection**: Compare current vs. latest available versions
2. **Backup Creation**: Comprehensive rollback point with all Vaultwarden assets
3. **Service Management**: Stop service for safe update
4. **Binary Update**: Cargo-based compilation and installation
5. **Web Vault Update**: Download and extract latest web interface
6. **Verification**: Post-update validation and service restart
7. **Rollback**: Automatic restoration on failure

## Configuration

### Module Configuration (`index.json`)

```json
{
    "metadata": {
        "schema_version": "1.0.0",
        "module_name": "vaultwarden",
        "description": "Vaultwarden password manager",
        "enabled": true
    },
    "config": {
        "directories": {
            "data_dir": "/var/lib/vaultwarden",
            "config_dir": "/etc/vaultwarden"
        },
        "installation": {
            "github_api_url": "https://api.github.com/repos/dani-garcia/vaultwarden/releases/latest"
        }
    }
}
```

### Production Configuration

The module works with the actual deployed Vaultwarden configuration:

```bash
# Environment file: /etc/vaultwarden.env
DOMAIN=https://vault.home.arpa
WEBSOCKET_ENABLED=true
ROCKET_ADDRESS=127.0.0.1
ROCKET_PORT=${ROCKET_PORT}
DATA_FOLDER=/var/lib/vaultwarden
ATTACHMENTS_FOLDER=/var/lib/vaultwarden/attachments
WEB_VAULT_FOLDER=/opt/vaultwarden/web-vault
DATABASE_URL=postgresql://vaultwarden:${DB_PASSWORD}@127.0.0.1/vaultwarden?sslmode=disable
ADMIN_TOKEN=${ADMIN_TOKEN}  # Argon2 hashed
LOG_FILE=/var/log/vaultwarden/vaultwarden.log
```

The systemd service includes comprehensive security hardening:
- `NoNewPrivileges=yes`
- `PrivateDevices=yes` 
- `PrivateTmp=yes`
- `ProtectHome=yes`
- `ProtectSystem=strict`
- `MemoryDenyWriteExecute=yes`
- Read-write access limited to data and log directories

### Default System Paths

The module manages these critical Vaultwarden components:

- **Binary**: `/opt/vaultwarden/vaultwarden`
- **Web Vault**: `/opt/vaultwarden/web-vault`
- **Data Directory**: `/var/lib/vaultwarden`
- **Configuration**: `/etc/vaultwarden.env`
- **Logs**: `/var/log/vaultwarden`
- **Attachments**: `/var/lib/vaultwarden/attachments` (local) and `/mnt/nas/vaultwarden` (NAS backup)

## Usage

### Command Line Interface

The module supports several operational modes:

#### Standard Update
```bash
python3 -m updates.modules.vaultwarden
```

#### Version Check
```bash
python3 -m updates.modules.vaultwarden --check
```

#### Comprehensive Verification
```bash
python3 -m updates.modules.vaultwarden --verify
```

#### Configuration Display
```bash
python3 -m updates.modules.vaultwarden --config
```

### Programmatic Usage

```python
from updates.modules.vaultwarden import main

# Standard update
result = main()

# Version check only
result = main(['--check'])

# Full verification
result = main(['--verify'])
```

## Update Process Details

### Binary Update Process

1. **Cargo Installation**: Uses Rust's cargo package manager with global CARGO_HOME at `/usr/local/cargo`
2. **Feature Configuration**: Builds with PostgreSQL support via `--features postgresql`
3. **System Integration**: Copies binary from `~/.cargo/bin/vaultwarden` to `/opt/vaultwarden/vaultwarden`
4. **Permission Management**: Sets `vaultwarden:vaultwarden` ownership and executable permissions

### Web Vault Update Process

1. **Version Detection**: Fetches latest release from `dani-garcia/bw_web_builds` repository
2. **Download**: Retrieves `bw_web_{version}.tar.gz` using curl
3. **Extraction**: Unpacks to `/opt/vaultwarden/web-vault` with `--strip-components=1`
4. **Integration**: Sets `vaultwarden:vaultwarden` ownership for service access

### Backup Strategy

The module creates comprehensive rollback points including:

- Vaultwarden binary (`/opt/vaultwarden/vaultwarden`)
- Web vault directory (`/opt/vaultwarden/web-vault`)
- Configuration file (`/etc/vaultwarden.env`)
- Data directory (`/var/lib/vaultwarden`)
- Log files (`/var/log/vaultwarden`)
- NAS backup location (`/mnt/nas/vaultwarden/attachments`)

## Return Values

### Success Response
```python
{
    "success": True,
    "updated": True,
    "old_version": "1.30.0",
    "new_version": "1.30.1",
    "verification": {
        "binary_exists": True,
        "service_active": True,
        "version": "1.30.1"
    },
    "backup_created": True
}
```

### Failure Response
```python
{
    "success": False,
    "error": "Update failed: compilation error",
    "restore_success": True,
    "restored_version": "1.30.0"
}
```

## Error Handling

### Automatic Rollback

On update failure, the module automatically:

1. Stops the service
2. Restores all backed-up files using StateManager
3. Restarts the service
4. Verifies restore success

### Common Failure Scenarios

- **Compilation Errors**: Cargo build failures trigger immediate rollback
- **Download Failures**: Network issues during web vault download
- **Permission Issues**: Insufficient privileges for file operations
- **Service Failures**: Post-update service startup problems

## Dependencies

### System Requirements

- **Rust/Cargo**: Global installation at `/usr/local/cargo` for binary compilation
- **systemd**: Service management with security hardening features
- **curl**: Web vault downloads from GitHub releases
- **PostgreSQL**: Database backend with dedicated user/database
- **Build Tools**: `build-essential`, `pkg-config`, `libssl-dev`, `libpq-dev`

### Python Dependencies

- Standard library modules (subprocess, json, urllib, etc.)
- HOMESERVER update system utilities (`updates.index`, `updates.utils.state_manager`)
- StateManager for backup operations (single backup per module)

## Integration

### HOMESERVER Ecosystem

This module integrates with:

- **Update Orchestrator**: Central update management
- **State Manager**: Backup and rollback system
- **Service Monitor**: Health checking and status reporting
- **Configuration System**: Centralized config management

### Service Dependencies

- **PostgreSQL**: Database backend with dedicated `vaultwarden` user and database
- **Reverse Proxy**: Web interface accessible via `https://vault.home.arpa`
- **systemd**: Service lifecycle management with security hardening
- **NAS Mount**: Backup storage at `/mnt/nas/vaultwarden`

## Troubleshooting

### Common Issues

#### Binary Not Found
```bash
# Check binary location
ls -la /opt/vaultwarden/vaultwarden

# Verify permissions
sudo -u vaultwarden /opt/vaultwarden/vaultwarden --version
```

#### Service Won't Start
```bash
# Check service status
systemctl status vaultwarden

# View logs
journalctl -u vaultwarden -f
```

#### Update Failures
```bash
# Run verification
python3 -m updates.modules.vaultwarden --verify

# Check cargo environment
echo $CARGO_HOME
ls -la ~/.cargo/bin/

# Check for rollback module error
# Note: Current implementation has a bug referencing non-existent rollback module
```

#### StateManager Integration

The module uses the HOMESERVER StateManager for backup and restore operations:

```python
# Create backup before update
state_manager = StateManager(backup_config["backup_dir"])
backup_success = state_manager.backup_module_state(
    module_name=SERVICE_NAME,
    description=f"pre_update_{current_version}_to_{latest_version}",
    files=files_to_backup,
    services=[SERVICE_NAME]
)

# Restore on failure
restore_success = state_manager.restore_module_state(SERVICE_NAME)
```

### Log Analysis

The module provides detailed logging for:

- Version detection and comparison
- Backup creation and verification
- Update process steps
- Service management operations
- Rollback procedures

## Security Considerations

### File Permissions

The module maintains proper ownership:
- Binary: `vaultwarden:vaultwarden` with `0755` permissions
- Data directories: `vaultwarden:vaultwarden` with `0750` permissions
- Configuration file: `vaultwarden:vaultwarden` with `0640` permissions (contains secrets)

### Backup Security

Rollback points include sensitive data:
- PostgreSQL database connection strings with passwords
- Hashed admin tokens in environment file
- User vault data and attachments
- SSL certificates and keys

Ensure backup directory has appropriate access controls and consider encryption for long-term storage.

## Performance Notes

### Update Duration

Typical update times:
- Version check: < 5 seconds
- Binary update: 2-10 minutes (compilation)
- Web vault update: 30-60 seconds
- Total process: 3-12 minutes

### Resource Usage

During updates:
- CPU: High during Cargo compilation
- Disk: Temporary space for downloads and backups
- Network: GitHub API calls and asset downloads

## Maintenance

### Backup Cleanup

The module automatically:
- Removes backups older than 30 days
- Maintains minimum of 5 recent backups
- Logs cleanup operations

### Configuration Updates

To modify module behavior:
1. Edit `index.json` configuration
2. Restart update service
3. Verify changes with `--config` flag

## License

This module is part of the HOMESERVER Update Management System and is licensed under the GNU General Public License v3.0. See the file headers for complete license information. 