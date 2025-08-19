# HOMESERVER Update Manager - Remote CLI Interface

## Overview

The HOMESERVER Update Manager provides a command-line interface for managing system updates and modules. This document details the CLI commands and options available for remote integration.

## CLI Interface

### Primary Command

```bash
/usr/local/lib/updates/updateManager.sh [OPTIONS]
```

## Available Options

### Update Operations

| Option | Description | Use Case |
|--------|-------------|----------|
| `--check` | Check for updates without applying them | Status queries, pre-flight validation |
| `--legacy` | Use legacy manifest-based updates | Fallback mode, compatibility |
| `--help`, `-h` | Show usage information | Documentation, troubleshooting |
| *(default)* | Run schema-based updates | Normal update operations |

### Module Management Operations

| Option | Arguments | Description | Use Case |
|--------|-----------|-------------|----------|
| `--enable <module>` | module name | Enable a module | Activate disabled functionality |
| `--disable <module>` | module name | Disable a module | Deactivate problematic modules |
| `--enable-component <module> <component>` | module, component | Enable specific component | Granular feature control |
| `--disable-component <module> <component>` | module, component | Disable specific component | Selective feature management |
| `--list-modules` | none | List all modules with status | System overview, inventory |
| `--status [module]` | optional module | Show module status/details | Detailed inspection |

## Usage Examples

### Basic Update Operations

```bash
# Check for available updates (non-destructive)
/usr/local/lib/updates/updateManager.sh --check

# Run full system updates
/usr/local/lib/updates/updateManager.sh

# Use legacy update system
/usr/local/lib/updates/updateManager.sh --legacy
```

### Module Management

```bash
# Enable/disable entire modules
/usr/local/lib/updates/updateManager.sh --enable website
/usr/local/lib/updates/updateManager.sh --disable adblock

# Enable/disable specific components within modules
/usr/local/lib/updates/updateManager.sh --enable-component website frontend
/usr/local/lib/updates/updateManager.sh --disable-component website premium

# List and inspect modules
/usr/local/lib/updates/updateManager.sh --list-modules
/usr/local/lib/updates/updateManager.sh --status website
```

### System Administration Workflow

```bash
# 1. Check current module status
/usr/local/lib/updates/updateManager.sh --list-modules

# 2. Disable problematic module
/usr/local/lib/updates/updateManager.sh --disable website

# 3. Check specific module details
/usr/local/lib/updates/updateManager.sh --status website

# 4. Enable specific components only
/usr/local/lib/updates/updateManager.sh --enable-component website frontend
/usr/local/lib/updates/updateManager.sh --enable-component website backend
/usr/local/lib/updates/updateManager.sh --disable-component website premium

# 5. Re-enable module after fixes
/usr/local/lib/updates/updateManager.sh --enable website

# 6. Run updates (only enabled modules will be processed)
/usr/local/lib/updates/updateManager.sh
```

## Output Format

### Log Format
All output follows the pattern:
```
[YYYY-MM-DD HH:MM:SS] [INFO] <message>
```

### Key Status Indicators

#### Success Patterns
```
[timestamp] [INFO] ✓ Update system completed successfully
[timestamp] [INFO] ✓ Module management operation completed successfully
[timestamp] [INFO] ✓ Module '<name>' enabled
[timestamp] [INFO] ✓ Component '<component>' enabled in module '<module>'
```

#### Error Patterns
```
[timestamp] [INFO] ✗ Update system failed with exit code <code>
[timestamp] [INFO] ✗ Module management operation failed with exit code <code>
[timestamp] [INFO] Error: Python orchestrator not found at <path>
[timestamp] [INFO] Module '<name>' not found
```

#### Progress Indicators
```
[timestamp] [INFO] Starting HOMESERVER update manager...
[timestamp] [INFO] Mode: <mode>
[timestamp] [INFO] Operation: <operation>
[timestamp] [INFO] Target: <module>
[timestamp] [INFO] Component: <component>
```

#### Module Listing Output
```
[timestamp] [INFO] Available modules:
[timestamp] [INFO] --------------------------------------------------------------------------------
[timestamp] [INFO] adblock         ENABLED    v1.1.0     Adblock module for Unbound DNS
[timestamp] [INFO] website         DISABLED   v1.0.0     HOMESERVER website frontend/backend update system
[timestamp] [INFO] --------------------------------------------------------------------------------
[timestamp] [INFO] Total: 2 modules (1 enabled, 1 disabled)
```

## Exit Codes

- **0:** Success
- **1:** General error (orchestrator missing, update failure)

## Requirements

- **User:** Must run as root or with appropriate sudo privileges
- **Working Directory:** Script handles path resolution internally
- **Environment:** No special environment variables required

## Help

```bash
/usr/local/lib/updates/updateManager.sh --help
```

This will display the complete usage information and examples. 