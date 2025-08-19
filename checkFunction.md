# HOMESERVER Update System --check Functionality Reference

## Overview

This document describes how the `--check` functionality is supposed to work in the HOMESERVER update system. Since every module has its own convoluted way of checking for changes, this serves as a reference for what's *expected* to happen rather than a standardized implementation.

## Macro Level (Orchestrator) --check Flow

### Shell Interface
```bash
/usr/local/lib/updates/updateManager.sh --check
```

### What Happens at Shell Level
1. Shell script parses `--check` flag
2. Calls Python orchestrator with `--check-only` flag
3. **NO LOG FILE CREATION** - output goes to stdout for user inspection
4. **NO ACTUAL UPDATES** - only status checking

### Python Orchestrator --check-only Processing
1. **Repository Sync**: Syncs from GitHub to check for orchestrator updates
2. **Schema Detection**: Identifies which modules need schema updates
3. **Module Status Collection**: Calls each enabled module with `--check` flag
4. **Summary Report**: Shows what updates are available without applying them

### Orchestrator --check Output Format
```
[timestamp] [INFO] Check-only mode: detecting updates without applying...
[timestamp] [INFO] Orchestrator is up to date
[timestamp] [INFO] All module schemas are up to date
[timestamp] [INFO] Checking OS module for available package updates...
[timestamp] [INFO] Check summary:
[timestamp] [INFO]   - No updates available
```

## Per-Module --check Expectations

### What Every Module Should Do with --check
- **NEVER** perform actual updates
- **NEVER** clone repositories
- **NEVER** create backups
- **NEVER** modify system state
- **ONLY** return status information
- **ONLY** check what would be updated

### Expected Module --check Response Format
```python
{
    "success": True,
    "enabled_components": ["component1", "component2"],
    "total_components": 2,
    "schema_version": "1.0.0",
    # Optional: module-specific status info
    "upgradable": 0,  # For OS module
    "current_version": "1.0.0",  # For version-aware modules
    "remote_version": "1.0.0"   # For version-aware modules
}
```

### What Modules Should NOT Do with --check
- Execute update logic
- Clone/copy files
- Modify system configuration
- Create temporary directories
- Perform expensive operations
- Return error codes for "no updates available"

## Current Module --check Implementations

### Linker Module (Reference Implementation)
```python
if "--check" in args:
    config = updater.config
    components = config.get('config', {}).get('target_paths', {}).get('components', {})
    enabled_components = [name for name, comp in components.items() if comp.get('enabled', False)]
    
    log_message(f"Linker module status: {len(enabled_components)} enabled components")
    return {
        "success": True,
        "enabled_components": enabled_components,
        "total_components": len(components),
        "schema_version": config.get("metadata", {}).get("schema_version", "unknown")
    }
```

**What it does RIGHT:**
- Returns status only
- No file operations
- No system modifications
- Clear, consistent response format

### OS Module (Complex Example)
```python
if "os" in enabled_modules:
    try:
        from . import run_update
        check_result = run_update("modules.os", ["--check"])
        
        if isinstance(check_result, dict) and check_result.get("upgradable", 0) > 0:
            count = check_result.get("upgradable", 0)
            log_message(f"  - OS module: {count} packages available for upgrade")
            content_updates_available.append({
                "module": "os",
                "count": count,
                "details": check_result
            })
    except Exception as e:
        log_message(f"  - OS module check failed: {e}", "WARNING")
```

**What it does DIFFERENTLY:**
- Calls another update function with --check
- Returns package counts
- Has complex nested logic
- Module-specific status information

## --check vs --version vs No Flags

### --check Flag
- **Purpose**: Check for available updates without applying them
- **Expected Behavior**: Return status, no modifications
- **Use Case**: Pre-flight validation, status queries

### --version Flag  
- **Purpose**: Get version information about the module
- **Expected Behavior**: Return version data, no modifications
- **Use Case**: Version queries, debugging

### No Flags (Default)
- **Purpose**: Perform actual update operations
- **Expected Behavior**: Full update process with version checking
- **Use Case**: Normal update operations

## Common --check Patterns (What to Look For)

### Good Patterns
```python
# Simple status return
if "--check" in args:
    return {"success": True, "status": "module_status_info"}

# Version comparison without updates
if "--check" in args:
    local_version = get_local_version()
    remote_version = get_remote_version()
    return {
        "success": True,
        "current_version": local_version,
        "remote_version": remote_version,
        "update_needed": local_version != remote_version
    }
```

### Bad Patterns (What to Avoid)
```python
# DON'T: Actually perform updates
if "--check" in args:
    return self.update()  # WRONG!

# DON'T: Clone repositories
if "--check" in args:
    self._clone_repository()  # WRONG!

# DON'T: Create backups
if "--check" in args:
    self._backup_current_installation()  # WRONG!
```

## Testing --check Functionality

### Manual Testing Commands
```bash
# Test shell interface
/usr/local/lib/updates/updateManager.sh --check

# Test individual module
cd /usr/local/lib && python3 -m updates.modules.linker --check

# Test Python orchestrator directly
cd /usr/local/lib && python3 -m updates.index --check-only
```

### Expected Test Results
- **Shell --check**: Should show available updates without applying them
- **Module --check**: Should return status without modifying system
- **No errors**: Should complete successfully even if no updates available

## Troubleshooting --check Issues

### Common Problems
1. **Module performs updates anyway**: Missing --check flag handling
2. **Module crashes on --check**: Exception in status checking logic
3. **No status returned**: Module doesn't handle --check flag
4. **Inconsistent response format**: Module returns different structure

### Debugging Steps
1. Check if module has `--check` in args handling
2. Verify module doesn't call update methods with --check
3. Ensure consistent return format
4. Test with `--check` flag explicitly

## Summary

The `--check` functionality is supposed to be a **read-only status check** that:
- Provides visibility into what updates are available
- Allows pre-flight validation before updates
- Never modifies system state
- Returns consistent status information

Since every module is different, this document serves as a reference for what the expected behavior should be, even if the actual implementations vary wildly in their complexity and approach.
