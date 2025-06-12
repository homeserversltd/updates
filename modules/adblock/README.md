# Adblock Update Module

## Overview

The adblock module manages network-level ad blocking for HOMESERVER by maintaining DNS blocklists for the Unbound DNS resolver. It downloads, processes, and combines multiple blocklist sources into a unified configuration that blocks ads and tracking domains at the DNS level.

## Purpose

- **Network-Level Blocking**: Blocks ads/trackers for all devices on the network
- **Unbound Integration**: Generates blocklist configuration for Unbound DNS resolver  
- **Multi-Source Aggregation**: Combines multiple blocklist sources for comprehensive coverage
- **Automatic Updates**: Refreshes blocklists when schema version changes

## Configuration (`index.json`)

### Schema Structure
```json
{
    "metadata": {
        "schema_version": "1.1.0",     // Update trigger
        "unbound_version": "1.19.0",   // Target Unbound version
        "module_name": "adblock",      // Module identifier
        "description": "Adblock module for Unbound DNS",
        "enabled": true                // Module status
    },
    "config": {
        "unbound_dir": "/etc/unbound",                    // Unbound config directory
        "blocklist_path": "/etc/unbound/blocklist.conf",  // Output blocklist file
        "sources": {
            "stevenblack": "https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts",
            "notracking": "https://raw.githubusercontent.com/notracking/hosts-blocklists/master/unbound/unbound.blacklist.conf"
        }
    }
}
```

### Configuration Options

- **`unbound_dir`**: Directory where Unbound configuration files are stored
- **`blocklist_path`**: Final location for the generated blocklist configuration
- **`sources`**: Dictionary of blocklist sources with descriptive names and URLs

### Automatic Version Detection

The `unbound_version` field is **automatically updated** on each module run:

1. **Detection Methods**:
   - Primary: `unbound -V` command output parsing
   - Fallback: `dpkg-query` for Debian/Ubuntu systems

2. **Version Normalization**:
   - Extracts clean version numbers (e.g., `1.17.1-2ubuntu0.1` → `1.17.1`)
   - Handles different package manager formats

3. **Configuration Update**:
   - Updates `index.json` with detected version
   - Logs version changes for tracking

4. **Command Line Access**:
   ```bash
   python3 index.py --version  # Check current Unbound version
   ```

## Operation Flow

### 1. Version Detection & Config Update
```python
update_config_version()  # Detect and update Unbound version
```

### 2. Configuration Loading
```python
config = load_config()  # Reads updated index.json
```

### 3. Source Download
- Downloads Steven Black's unified hosts file (hosts format)
- Downloads NoTracking's Unbound blacklist (Unbound format)
- Creates empty files if downloads fail (graceful degradation)

### 4. Format Processing
- **Hosts Format**: Converts `0.0.0.0 domain.com` → `local-zone: "domain.com" always_nxdomain`
- **Unbound Format**: Uses directly (already in correct format)

### 5. List Combination
- **Domain-Level Deduplication**: Extracts and normalizes domains from both sources
- **Format Normalization**: Handles trailing dots, case differences, and action types
- **Intelligent Merging**: Combines `always_null` and `always_nxdomain` entries
- **Sorted Output**: Generates consistent, alphabetically sorted blocklist

### 6. Safe Installation
- Creates backup using StateManager before changes
- Installs new blocklist atomically
- Restarts Unbound service if active

## Update Triggers

The module has two distinct update mechanisms:

1. **Blocklist Updates** (via cron):
   - Runs daily at 3 AM with random delay
   - Downloads and processes latest blocklists
   - Independent of schema version
   - Logs output to `/var/log/homeserver/adblock.log`

2. **Module Code Updates** (triggered by schema version):
   - `metadata.schema_version` changes trigger module code updates
   - Updates `__init__.py`, `index.json`, `index.py`, `README.md`, `adblock.cron`
   - Used to modify blocklist sources, cron schedule, or module behavior
   - Does not affect daily blocklist update frequency

This separation ensures blocklists stay current while allowing module code and cron configuration to be updated independently.

## Error Handling

### Graceful Degradation
- **Download Failures**: Creates empty files, continues processing
- **Service Issues**: Logs warnings but doesn't fail update
- **Missing Directories**: Validates paths before processing

### Backup Safety
- Uses StateManager for reliable state backup/restore
- Atomic file operations prevent corruption
- Service restart only if Unbound is already active

## File Structure

```
adblock/
├── __init__.py          # Module interface and integrity checking
├── index.json          # Configuration and schema version
├── index.py            # Main update logic
└── README.md           # This documentation
```

## Integration Points

### Orchestrator Interface
- **Entry Point**: `main(args=None)` function
- **Return Value**: 
  - `True` for successful updates
  - `False` for failed updates
  - Dictionary with `{"success": bool, "version": str}` for version checks
- **Logging**: Uses `[adblock]` prefix for all messages

### System Dependencies
- **Unbound DNS**: Target service for blocklist configuration
- **systemctl**: Service management for Unbound restarts
- **Network Access**: Downloads blocklist sources via HTTPS
- **StateManager**: For reliable state backup/restore

## Blocklist Sources

### Steven Black's Unified Hosts
- **Format**: Traditional hosts file (`0.0.0.0 domain.com`)
- **Coverage**: Comprehensive ad/malware/tracking domains
- **Update Frequency**: Regular community updates

### NoTracking Unbound Blacklist
- **Format**: Native Unbound configuration
- **Coverage**: Privacy-focused tracking domain blocks
- **Update Frequency**: Maintained specifically for privacy

## Example Usage

### Command Line Options
```bash
cd /usr/local/lib/updates/modules/adblock

# Full blocklist update with automatic version detection
python3 index.py

# Check current Unbound version only
python3 index.py --version
```

### Manual Update
```bash
# Run adblock update directly
python3 -c "from updates.modules.adblock import main; main()"
```

### Orchestrator Integration
```python
# Called automatically by update orchestrator
from updates.modules.adblock import main
result = main()
print(f"Adblock update: {'success' if result else 'failed'}")
```

## Monitoring

### Log Messages
```
[adblock] Updated Unbound version in config: 1.17.1 → 1.19.0
[adblock] Starting adblock update...
[adblock] Downloading blocklists...
[adblock] Processing hosts file...
[adblock] Combining blocklists...
[adblock] Combined and deduplicated 525400 unique domains
[adblock] Backed up state using StateManager
[adblock] Installed new blocklist at /etc/unbound/blocklist.conf
[adblock] Restarting unbound service...
[adblock] Blocklist update completed
```

### Success Indicators
- Return value `True` from `main()` function
- New blocklist file created at configured path
- Unbound service restarted (if was active)
- State backup created successfully via StateManager

## Troubleshooting

### Common Issues

#### Unbound Directory Missing
```
[adblock] Error: /etc/unbound does not exist
```
**Solution**: Ensure Unbound is installed and configured

#### Download Failures
```
[adblock] Warning: Failed to download https://...
```
**Solution**: Check network connectivity and source availability

#### Service Restart Issues
```
[adblock] Warning: Failed to restart unbound: ...
```
**Solution**: Check systemctl permissions and Unbound configuration

### Validation
```bash
# Check blocklist was created
ls -la /etc/unbound/blocklist.conf

# Verify Unbound configuration
unbound-checkconf

# Test DNS blocking
dig @localhost blocked-domain.com
```

## Schema Evolution

To trigger updates:
1. Modify blocklist sources in `index.json`
2. Increment `metadata.schema_version`
3. Commit to updates repository
4. Orchestrator will detect version change and run update

The module follows the established pattern of configuration-driven updates with schema versioning for reliable, atomic blocklist management.

## Enhanced Deduplication

### Problem Solved
The original implementation had duplicate warnings in Unbound logs due to format inconsistencies:
```
warning: duplicate local-zone 03e.info.
```

### Root Cause
Different sources used different formats:
- **Steven Black**: `local-zone: "domain.com" always_nxdomain` (no trailing dot)
- **NoTracking**: `local-zone: "domain.com." always_null` (with trailing dot)

### Solution
**Domain-level deduplication** that normalizes before comparison:

```python
def extract_domain(line):
    """Extract and normalize domain from Unbound local-zone line."""
    domain = parts[1].rstrip('.').lower()  # Remove dots, normalize case
    return domain

# Result: Intelligent merging eliminates format-based duplicates
domains = set()  # Only unique normalized domains
```

### Benefits
- **Eliminates Unbound warnings** about duplicate local-zones
- **Reduces file size** by removing format-based duplicates  
- **Consistent output** with standardized `always_nxdomain` action
- **Better performance** with fewer duplicate DNS lookups 