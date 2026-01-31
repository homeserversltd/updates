# Migrations Module

## Purpose

The migrations module provides a controlled mechanism for executing one-time system-wide changes across all HOMESERVER installations. Unlike hotfixes that target specific version conditions, migrations run sequentially in a deterministic order, ensuring consistent system evolution.

## What It Does

- **Sequential Execution**: Runs migration scripts in strict numerical order from index.json
- **State Tracking**: Tracks which migrations have completed successfully via `has_run` flag
- **Idempotent Design**: All migrations must be safe to run multiple times
- **Automatic Retry**: Failed migrations retry on next update cycle until successful
- **Comprehensive Logging**: Full visibility into migration execution and failures

## Why It Matters

System evolution requires carefully orchestrated changes that affect core infrastructure. The migrations module ensures that:

- **Database schema changes** roll out consistently across all installations
- **Configuration updates** happen in the right order with proper dependencies
- **Service migrations** (like KEA CSV to PostgreSQL) execute safely
- **System-wide refactoring** proceeds in controlled, reversible steps
- **Failed migrations** don't break the system and can retry automatically

## How It Works

### Ladder Logic Execution

Migrations execute in strict order as defined in `index.json`:

1. Load all migrations from configuration
2. For each migration in order where `has_run=false`:
   - Execute the corresponding shell script from `src/`
   - Capture all output to migration log
   - On success (exit code 0): mark `has_run=true` in index.json
   - On failure (exit code != 0): log error, leave `has_run=false`, continue to next update
3. Next update cycle retries all migrations where `has_run=false`

### Migration Scripts

- **Location**: `src/00000001.sh`, `src/00000002.sh`, etc.
- **Naming**: 8-digit zero-padded numbers (00000001 through 99999999)
- **Execution**: Run as root with full system access
- **Timeout**: 10 minutes per migration (configurable)
- **Environment**: Access to `/root/key/skeleton.key` (Factory Access Key)

## Critical Rules

### IDEMPOTENCY IS MANDATORY

Every migration MUST be idempotent. Running the same migration multiple times should:
- Detect if already applied and exit successfully
- Never cause data loss or corruption
- Leave the system in a consistent state

Example idempotency checks:
```bash
# Check if already migrated
if grep -q '"type": "postgresql"' /etc/kea/kea-dhcp4.conf; then
    echo "Migration already applied, exiting successfully"
    exit 0
fi

# Check if database already exists
if sudo -u postgres psql -lqt | cut -d \| -f 1 | grep -qw kea; then
    echo "KEA database already exists, skipping creation"
fi
```

### NEVER LEAVE SYSTEM BROKEN

Migrations must handle failures gracefully:
- Create backups before modifying critical files
- Test operations before committing changes
- Restore from backup on failure
- Exit with code 1 on failure to trigger retry

Example error handling:
```bash
# Backup before modification
cp /etc/kea/kea-dhcp4.conf /etc/kea/kea-dhcp4.conf.backup

# Try operation
if ! update_config; then
    echo "ERROR: Config update failed, restoring backup"
    cp /etc/kea/kea-dhcp4.conf.backup /etc/kea/kea-dhcp4.conf
    exit 1
fi

# Verify service restarts
if ! systemctl restart kea-dhcp4-server.service; then
    echo "ERROR: Service failed to start, restoring backup"
    cp /etc/kea/kea-dhcp4.conf.backup /etc/kea/kea-dhcp4.conf
    systemctl restart kea-dhcp4-server.service
    exit 1
fi
```

### USE FACTORY ACCESS KEY

PostgreSQL and other secure services use the Factory Access Key (FAK):
```bash
# Read FAK
FAK=$(cat /root/key/skeleton.key | tr -d '\n')

# Use in PostgreSQL operations
sudo -u postgres psql -c "CREATE USER kea WITH PASSWORD '$FAK';"
```

The FAK provides consistent authentication across all HOMESERVER services.

## Migration Numbering Scheme

- **00000001-09999999**: System infrastructure migrations
- **10000000-19999999**: Service migrations
- **20000000-29999999**: Database schema migrations
- **30000000-39999999**: Configuration migrations
- **40000000-49999999**: Security updates
- **50000000-99999999**: Reserved for future use

Gaps in numbering are intentional to allow insertion of urgent migrations.

## Adding New Migrations

1. **Create the script**: `src/NNNNNNNN.sh` with proper idempotency checks
2. **Make executable**: `chmod +x src/NNNNNNNN.sh`
3. **Add to index.json**:
   ```json
   {
     "id": "NNNNNNNN",
     "description": "What this migration does",
     "has_run": false
   }
   ```
4. **Test locally**: Run the script multiple times to verify idempotency
5. **Commit to repository**: Push to main updates repository (migrations is part of updates module)
6. **Deploy**: Update system will automatically deploy new migration to all systems

## Logging

All migration output goes to:
- **Primary log**: `/var/log/homeserver/migrations.log`
- **Update log**: `/var/log/homeserver/update.log` (summary)

Each migration execution includes:
- Timestamp
- Migration ID and description
- Full stdout/stderr output
- Exit code
- Execution duration

## Integration with Update System

The migrations module integrates seamlessly with HOMESERVER's update orchestrator:

1. **Schema updates** deploy new migrations from main updates repository (migrations is part of the updates module)
2. **Module execution** runs migrations module (enabled: true)
3. **Sequential processing** executes pending migrations in order
4. **State persistence** saves `has_run` status to index.json
5. **Automatic retry** re-runs failed migrations on next update

## Key Differences from Hotfix Module

| Feature | Migrations | Hotfixes |
|---------|-----------|----------|
| Execution order | Sequential (strict) | Any order (version checks) |
| Version checking | None | Complex (module/binary/file) |
| Retry behavior | Automatic until success | Run once if conditions met |
| Use case | System evolution | Emergency patches |
| Idempotency | Mandatory | Recommended |
| Naming | 8-digit numbers | Descriptive IDs |

## Example: KEA PostgreSQL Migration

Migration `00000001` demonstrates proper migration design:

**Idempotency checks:**
- Verify KEA not already using PostgreSQL
- Check if database already exists
- Test if schema already initialized

**Safe execution:**
- Backup config before modification
- Create database before modifying config
- Test service restart
- Restore backup on any failure

**Comprehensive logging:**
- Log each step for debugging
- Capture error output
- Exit with appropriate code

This pattern ensures reliable, repeatable migrations across all HOMESERVER installations.

## Example: CRA to Vite (00000006)

Migration `00000006` completes the frontend build-tool migration from Create React App to Vite across the platform. It is idempotent (exits early if `vite.config.ts` exists and `react-scripts` is gone), updates `package.json`, creates `vite.config.ts` with `process.env` defines, ensures `public/index.html` has the Vite entry, runs `npm install` and `npm run build`, and restarts Gunicorn. Output remains in `build/`; Flask contract unchanged.

## Troubleshooting

### Migration Stuck in Failed State

If a migration repeatedly fails:

1. Check migration log: `tail -f /var/log/homeserver/migrations.log`
2. Run migration manually: `bash /usr/local/lib/updates/modules/migrations/src/NNNNNNNN.sh`
3. Fix underlying issue
4. Let update system retry automatically

### Manual State Reset

If you need to re-run a completed migration:

```bash
# Edit index.json
vim /usr/local/lib/updates/modules/migrations/index.json

# Change "has_run": true to "has_run": false for target migration

# Run update to trigger re-execution
@updateManager.sh
```

### Migration Takes Too Long

Default timeout is 10 minutes. For longer migrations:
- Break into multiple smaller migrations
- Each migration should complete one atomic change
- Use migration dependencies to enforce order

## Best Practices

1. **Keep migrations small**: One logical change per migration
2. **Test exhaustively**: Run 5+ times locally before deploying
3. **Log verbosely**: More logging is better than less
4. **Fail fast**: Detect errors early and exit immediately
5. **Backup everything**: Before modifying any critical files
6. **Verify success**: Test that change actually worked before marking complete
7. **Document intent**: Comments explaining why, not just what

## Security Considerations

- Migrations run as root with full system access
- Scripts can access skeleton.key for service authentication
- Never log sensitive data (passwords, keys)
- Validate all user input if migrations accept parameters
- Use absolute paths to prevent PATH manipulation

## Future Enhancements

Potential improvements to the migrations system:

- Migration dependencies (require other migrations first)
- Rollback scripts for complex migrations
- Dry-run mode to preview changes
- Migration execution time tracking
- Automatic backup before each migration
- Migration verification tests

---

The migrations module provides the foundation for controlled, reliable evolution of HOMESERVER systems. By enforcing idempotency, providing automatic retry, and maintaining strict execution order, it ensures that all installations remain consistent and up-to-date.

