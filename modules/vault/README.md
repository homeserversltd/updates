# Vault Module

## Purpose

The vault module manages the `/vault/scripts` directory and its contents for HOMESERVER systems. It provides automated deployment, version checking, and maintenance of vault-related scripts and Python modules that handle critical system operations like NAS management, VPN integration, and service orchestration.

## What It Does

- **Script Management**: Deploys and maintains shell scripts for NAS operations, drive mounting, and service management
- **Python Module Management**: Manages Python modules for VPN integration, configuration management, and system utilities
- **Version Control**: Tracks and updates vault scripts based on remote repository versions
- **Permission Management**: Ensures proper ownership and permissions for all vault scripts and modules
- **Backup Integration**: Creates backups before updates and provides rollback capabilities

## Why It Matters

The vault scripts are critical components of HOMESERVER's infrastructure management:

- **NAS Operations**: Scripts for mounting, unmounting, and managing network-attached storage
- **VPN Integration**: Python modules for Private Internet Access (PIA) VPN configuration and management
- **Service Orchestration**: Scripts for starting, stopping, and managing various HOMESERVER services
- **System Utilities**: Configuration management, logging, and template processing utilities

## Key Components

### Shell Scripts
- `closeNAS.sh` - NAS shutdown procedures
- `exportNAS.sh` - NAS export operations
- `exportServiceSuite.sh` - Service suite export functionality
- `init.sh` - Vault initialization script
- `mountDrive.sh` - Drive mounting operations
- `unmountDrive.sh` - Drive unmounting operations

### Python Modules
- `transmission.py` - Transmission torrent client management
- `teardown_standalone.py` - Standalone teardown operations
- `src/config.py` - Configuration management
- `src/logger.py` - Logging utilities
- `src/vpn.py` - VPN management core
- `src/pia/` - Private Internet Access VPN integration modules

## Integration with HOMESERVER

The vault module integrates with HOMESERVER's update management system to ensure vault scripts are always current and properly configured. It works alongside other modules to maintain the complete HOMESERVER infrastructure.

## Configuration

The module uses `index.json` to define:
- Repository source for vault scripts
- Individual file management settings
- Version tracking and update requirements
- Permission and ownership settings

## Key Features

- **Automated Updates**: Pulls latest scripts from configured repository
- **Version Tracking**: Compares local and remote versions to determine update needs
- **Atomic Updates**: Uses temporary files and atomic moves to prevent corruption
- **Permission Management**: Automatically sets correct ownership and permissions
- **Backup and Rollback**: Creates backups before updates with rollback capability
- **Selective Updates**: Can enable/disable individual files via `keepUpdated` flag

This module ensures HOMESERVER's vault scripts remain current, secure, and properly configured for optimal system operation.
