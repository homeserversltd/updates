# Keyman Update Module

## Workflow Diagram

```mermaid
flowchart TD
    A[Module Entry] --> B{Command Line Args?}
    
    B -->|--check| C[Check Mode: File Status]
    B -->|No Args| D[Apply Mode: Update Credential Tools]
    
    C --> C1[Load Module Config]
    C1 --> C2[Filter Enabled Files]
    C2 --> C3[Check File Existence at /vault/keyman]
    C3 --> C4[Generate State Report]
    C4 --> C5[Save to manifest.state.json]
    C5 --> C6[Return Drift Analysis]
    
    D --> E[Check Version Update Needed]
    E --> F{Update Required?}
    
    F -->|No| G[Skip - Already Current]
    F -->|Yes| H[Version Check: Clone Keyman Repo]
    
    H --> I[Compare Local vs Remote VERSION]
    I --> J{Content Changed?}
    
    J -->|No| K[Skip - No Changes]
    J -->|Yes| L[Create Backup: All Credential Tools]
    
    L --> M[Initialize State Manager]
    M --> N[Backup Module State]
    N --> O[Process Each Keyman Tool]
    
    O --> P[Resolve Source Path from Repo]
    P --> Q[Create Temporary File]
    Q --> R[Copy Source to Temp]
    R --> S[Set Secure Permissions (700)]
    
    S --> T[Atomic Replace: Temp → /vault/keyman/]
    T --> U[Track Changed Files]
    U --> V{More Tools?}
    
    V -->|Yes| O
    V -->|No| W[Update Local content_version]
    
    W --> X[Return Success Status]
    
    G --> Y[Return: No Update Needed]
    K --> Z[Return: No Changes]
    
    style A fill:#e1f5fe
    style X fill:#c8e6c9
    style G fill:#c8e6c9
    style K fill:#c8e6c9
    style C6 fill:#c8e6c9
```

## Overview

The Keyman update module manages credential management tools at `/vault/keyman/` using version-based updates from the [homeserversltd/keyman](https://github.com/homeserversltd/keyman) Git repository.

## Key Features

- **Version-Based Updates**: Compares local `content_version` with remote `VERSION` file
- **Atomic Updates**: All-or-nothing deployment with automatic rollback
- **Secure Permissions**: All files deployed with restrictive 700 permissions
- **Repository Sync**: Automatic Git repository synchronization
- **State Management**: Comprehensive backup and restore functionality

## Managed Files

The module manages the complete keyman credential management suite:

### Core Scripts
- `keystartup.sh` - Initialize key system infrastructure
- `newkey.sh` - Create new service credentials
- `exportkey.sh` - Export decrypted credentials to ramdisk
- `deletekey.sh` - Remove service credentials
- `change_service_suite_key.sh` - Manage encryption key rotation

### Specialized Tools
- `updateLuksKey.sh` - Update LUKS encrypted drive passwords
- `updateTransmissionKey.sh` - Update Transmission daemon credentials
- `utils.sh` - Shared utility functions

### System Components
- `keyman-crypto` - Compiled encryption binary
- `keyman-crypto.c` - Source code for encryption operations
- `Makefile` - Build system for crypto binary

### Documentation
- `README.md` - Complete keyman documentation
- `LICENSE` - GPL-3.0 license
- `VERSION` - Version tracking file

## Deployment Location

All keyman tools are deployed to `/vault/keyman/` with the following characteristics:

- **Path**: `/vault/keyman/<filename>`
- **Owner**: `root:root`
- **Permissions**: `700` (read/write/execute for owner only)
- **Security**: Located on encrypted vault partition

## Update Behavior

### Version Check Process
1. Read local `content_version` from module `index.json`
2. Clone remote repository to temporary directory
3. Read remote `VERSION` file
4. Compare versions for update necessity

### Update Process
1. **Backup**: Create state backup of existing tools
2. **Repository Sync**: Ensure latest code from GitHub
3. **Atomic Deployment**: Replace all files simultaneously
4. **Permission Setting**: Apply secure 700 permissions
5. **Version Update**: Update local `content_version`

### File Management
- Files are replaced atomically using temporary staging
- All operations logged with detailed context
- Failed updates automatically trigger rollback
- State management ensures system consistency

## Integration with Bootstrap

The keyman update module works in conjunction with bootstrap initialization:

- **Bootstrap**: Handles initial key system setup and directory creation
- **Update Module**: Manages ongoing tool updates and version synchronization
- **Separation**: Clean division of initialization vs. maintenance responsibilities

## Security Considerations

- **Encrypted Storage**: All tools stored on encrypted `/vault` partition
- **Restrictive Permissions**: 700 permissions prevent unauthorized access
- **Secure Updates**: Atomic updates prevent partially-deployed states
- **Git Repository**: Source code maintained in version-controlled repository
- **Backup Protection**: State backups ensure recovery capabilities

## Configuration

The module is configured via `index.json`:

```json
{
  "metadata": {
    "schema_version": "1.0.0",
    "content_version": "1.0.0", 
    "enabled": true,
    "priority": 2
  },
  "repo": {
    "url": "https://github.com/homeserversltd/keyman.git",
    "branch": "master"
  },
  "files": [
    { "source": "keystartup.sh", "keepUpdated": true, "mode": "700" }
  ]
}
```

## Usage

The module is executed automatically by the update orchestrator:

```bash
# Check mode (status only)
python3 /var/local/lib/updates/modules/keyman/index.py --check

# Apply mode (perform updates)
python3 /var/local/lib/updates/modules/keyman/index.py
```

## Benefits

- **Centralized Management**: Single source of truth for credential tools
- **Version Control**: Full Git history of tool changes
- **Automatic Updates**: No manual intervention required
- **Security Focus**: Proper permissions and encrypted storage
- **System Integration**: Seamless integration with HOMESERVER update system
