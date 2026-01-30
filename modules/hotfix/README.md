# Hotfix Module

## Purpose

The hotfix module provides universal emergency patch deployment capabilities for HOMESERVER systems. It serves as a powerful safety net that can target any component in the system with intelligent version checking and script-based execution.

## What It Does

- **Universal Targeting**: Fix any software, module, or system component across the entire HOMESERVER stack
- **Intelligent Version Checking**: Only applies fixes when version conditions are met
- **Script-Based Execution**: Simple shell scripts handle complex fixes and system modifications
- **Flexible Conditions**: Support for module schemas, binary versions, file existence, and custom conditions
- **Safe Execution**: Built-in timeouts, error handling, and execution tracking

## Why It Matters

Even the most carefully designed systems sometimes need emergency fixes. HOMESERVER's hotfix module provides a controlled way to deploy critical patches when:

- **Security Vulnerabilities**: Immediate patches for newly discovered security issues
- **Critical Bugs**: Fixes for system-breaking bugs that can't wait for the next release
- **Configuration Errors**: Corrections to configuration files that prevent proper operation
- **Service Recovery**: Emergency repairs to restore failed services
- **Compatibility Issues**: Quick fixes for compatibility problems with new environments
- **System Maintenance**: One-off fixes that need to run once across all installations

## How It Works

### Target-Based System
Each hotfix is defined as a "target" with:
- **Unique ID**: Identifier for the hotfix
- **Description**: What the hotfix does
- **Target ID**: What system component it targets
- **Version Check**: Conditions that determine if the hotfix should run
- **Execution Tracking**: Prevents duplicate runs

### Version Check Types

1. **Module Schema**: Check if a module's schema version is below a threshold
   ```json
   "version_check": {
     "type": "module_schema",
     "module": "gogs",
     "max_version": "0.1.7"
   }
   ```

2. **Binary Version**: Check if a binary's version is below a threshold
   ```json
   "version_check": {
     "type": "binary_version",
     "binary": "/usr/bin/git",
     "max_version": "2.30.0"
   }
   ```

3. **File Existence**: Check if a file exists (or doesn't exist)
   ```json
   "version_check": {
     "type": "file_exists",
     "path": "/etc/homeserver.factory",
     "invert": true
   }
   ```

4. **Always Run**: Apply the hotfix unconditionally
   ```json
   "version_check": {
     "type": "always",
     "value": true
   }
   ```

### Script Execution
- Each target runs a corresponding script from the `src/` directory
- Scripts are named `{target_id}.sh` (e.g., `gogs_repository_fix.sh`)
- Scripts have 5-minute execution timeout
- All output is logged for debugging

## Key Features

- **Universal Reach**: Can fix any component in the HOMESERVER system
- **Smart Conditions**: Only runs when actually needed based on version checks
- **Simple Scripts**: Easy to write and maintain shell script fixes
- **Execution Tracking**: Prevents duplicate runs with `has_run` flag
- **Error Handling**: Failed targets don't break other hotfixes
- **Comprehensive Logging**: Full visibility into what's happening

## Integration with HOMESERVER

The hotfix module integrates with HOMESERVER's update system to provide controlled emergency patching. It can target any module, service, or system component while respecting the existing backup and rollback infrastructure.

This module serves as HOMESERVER's universal emergency response system - a powerful tool that can fix anything, anywhere, when you need it most.

## Current Hotfixes

- **homeserver_logrotate**: Install log rotation and cron for /var/log/homeserver/*.log
