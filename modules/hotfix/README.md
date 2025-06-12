# Hotfix Module

Emergency patch management system for HOMESERVER with pool-based operations and graceful failure handling.

## Overview

The hotfix module provides a robust system for applying emergency fixes to any system files not managed by other specialized modules. It uses a pool-based approach where related files are grouped together with shared closure commands, ensuring atomic operations and graceful degradation when customer modifications conflict with fixes.

## Design Philosophy

- **Pool-based transactions**: Related files are grouped into logical pools that succeed or fail as a unit
- **Graceful failure**: If a pool fails, it reverts cleanly and continues processing other pools
- **Customer-first**: Respects customer modifications by reverting when conflicts are detected
- **Closure-driven validation**: Success is determined by whether the system can build/restart, not file comparison
- **No modification detection**: Cannot reliably detect customer changes, so backup/attempt/revert is the strategy

## Architecture

### Pool Structure

Hotfixes are organized into pools where each pool contains:
- **Operations**: List of files to copy from `src/` to target destinations
- **Closure commands**: Build/restart commands that validate the changes work
- **Atomic behavior**: All files in a pool succeed together or fail together

### Transaction Flow

For each pool:
1. **Backup Phase**: StateManager backs up ALL destination files in the pool
2. **Apply Phase**: Copy all source files to their destinations
3. **Closure Phase**: Execute closure commands (npm build, service restarts, etc.)
4. **Result**: 
   - **Success**: Continue to next pool
   - **Failure**: Restore ALL files in pool, re-run closure commands, mark pool failed, continue

After all pools complete:
5. **Final Closure Phase**: Execute finalClosure commands for system-wide validation
   - Only runs if all pools completed successfully
   - Performs health checks, integration tests, or cleanup operations
   - Failure logs error but doesn't trigger pool rollbacks

## Configuration (index.json)

```json
{
  "metadata": {
    "schema_version": "1.1.0",
    "description": "Emergency hotfixes and critical patches"
  },
  "pools": [
    {
      "id": "website_security_patch",
      "description": "Frontend security fixes for authentication components",
      "operations": [
        {
          "target": "src/auth.tsx",
          "destination": "/var/www/homeserver/src/components/auth.tsx"
        },
        {
          "target": "src/header.tsx", 
          "destination": "/var/www/homeserver/src/components/header.tsx"
        },
        {
          "target": "src/login.tsx",
          "destination": "/var/www/homeserver/src/components/login.tsx"
        }
      ],
      "closure": [
        "cd /var/www/homeserver",
        "npm build",
        "systemctl restart homeserver"
      ]
    },
    {
      "id": "backend_config_fix",
      "description": "Update backend configuration files",
      "operations": [
        {
          "target": "src/config.py",
          "destination": "/var/www/homeserver/backend/config.py"
        }
      ],
      "closure": [
        "systemctl restart gunicorn"
      ]
    }
  ],
  "finalClosure": [
    "curl -f http://localhost:5000/health",
    "systemctl is-active homeserver"
  ]
}
```

### Pool Properties

- **id**: Unique identifier for the pool
- **description**: Human-readable description of what this pool fixes
- **operations**: Array of file copy operations
  - **target**: Source file path relative to `src/` directory
  - **destination**: Absolute path where file should be placed
- **closure**: Array of commands to run after all files are copied

### Global Properties

- **finalClosure**: Array of commands to run after ALL pools have been processed successfully
  - Used for system-wide validation and health checks
  - Only executes if all pools complete successfully
  - Failure in finalClosure logs error but doesn't rollback successful pools

## Source File Management

All hotfix files are stored in the `src/` directory within the module. When schema version is bumped:

1. Entire pool of hotfixes is re-applied
2. Source files represent the "current correct version" of each target
3. No need to track incremental changes - just maintain latest correct version

### Adding New Hotfixes

1. Place corrected file in `src/` directory
2. Add entry to appropriate pool in `index.json`
3. Bump `schema_version` in metadata
4. Deploy via normal update mechanism

## Rollback Strategy

### StateManager Integration

The hotfix module uses the existing StateManager system for backup and restore:

- **Backup scope**: Per-pool (all destination files in a pool)
- **Restore trigger**: Any closure command failure
- **Rollback behavior**: Restore entire pool, re-run closure commands
- **Continuation**: Failed pools don't stop processing of subsequent pools

### Version Control Rollback

For more significant rollbacks, the existing version control system can checkout previous versions of the entire hotfix module:

```bash
# Rollback entire hotfix module to previous version
version_control.checkout_module_version("hotfix", "1.0.9")
```

## Failure Scenarios & Handling

### Customer Modification Conflicts

**Scenario**: Customer has modified files that hotfix tries to update

**Detection**: Closure commands fail (npm build fails, services won't start)

**Response**: 
1. StateManager restores customer's original files
2. Re-run closure commands to return system to working state
3. Log pool as failed but continue processing other pools
4. Customer keeps their modifications, system remains functional

### Partial Pool Failures

**Scenario**: Some files copy successfully, but closure commands fail

**Response**:
1. All files in the pool are restored (atomic rollback)
2. Closure commands re-run to ensure clean state
3. Pool marked as failed
4. Subsequent pools continue processing

### Critical System Files

**Scenario**: Hotfix affects files critical to system operation

**Design**: Keep hotfix pools small and focused. If a pool affects critical files, ensure closure commands can detect problems and rollback gracefully.

## Use Cases

### Website Security Fix
- Update multiple React components for security vulnerability
- Single pool ensures all related changes applied together
- npm build validates changes work with existing codebase
- Service restart confirms application runs correctly

### Configuration File Updates
- Update backend configuration files
- Service restart validates configuration is correct
- Graceful rollback if new config breaks service startup

### Script Corrections
- Replace broken utility scripts
- Validation through script execution or service that depends on them

### System-Wide Validation (finalClosure)
- Health check endpoints after all changes applied
- Integration testing across multiple updated components
- Cache clearing or state cleanup after all pools complete
- Notification systems that changes have been applied successfully

## Best Practices

### Pool Design
- **Keep pools focused**: Group only truly related files together
- **Make closure commands robust**: Ensure they can detect if changes work
- **Test rollback paths**: Verify that closure commands work on restored files

### Source File Management
- **Single source of truth**: Each src file represents current correct version
- **No incremental tracking**: Replace entire file, don't try to patch
- **Version through schema**: Use schema_version bumps to trigger re-application

### Customer Considerations
- **Expect modifications**: Customers will modify system files
- **Graceful degradation**: Failed pools shouldn't break the system
- **Preserve functionality**: Customer modifications take precedence over hotfixes

## Integration with Broader System

### Schema Versioning
- Hotfix module participates in standard schema versioning
- Schema bump triggers complete re-application of all pools
- Leverages existing update orchestration infrastructure

### StateManager Integration
- Uses standard backup/restore patterns from StateManager
- Consistent with other module rollback strategies
- No special rollback machinery needed

### Logging and Observability
- Pool success/failure tracked in standard update logs
- Failed pools logged with reasons (closure command failures)
- Provides visibility into which hotfixes work across customer base

## Development Workflow

### Emergency Hotfix Process
1. **Identify problem**: Broken file needs immediate replacement
2. **Create fix**: Place corrected file in `src/` directory
3. **Update config**: Add to appropriate pool in `index.json`
4. **Version bump**: Increment `schema_version`
5. **Deploy**: Push to repository, let schema versioning trigger update
6. **Monitor**: Check logs for pool success/failure across deployments

### Testing Hotfixes
- Test closure commands succeed with new files
- Test closure commands succeed after rollback
- Verify pool atomicity (all files restored on failure)
- Test with customer-like modifications to target files

## Migration from Legacy System

The new pool-based system replaces the previous operation-based approach:

**Legacy**: Individual operations with complex rollback machinery
**New**: Pool-based transactions with StateManager integration

**Migration benefits**:
- Simpler architecture leveraging existing systems
- Better customer modification handling
- More reliable rollback through closure command validation
- Atomic transactions for related changes
