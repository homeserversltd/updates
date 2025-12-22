# MkDocs Update Module

## Purpose

The MkDocs update module manages three components of the HOMESERVER documentation system:

1. **MkDocs Software**: The documentation generator application itself
2. **Material Theme**: The MkDocs Material theme package
3. **Documentation Content**: The actual documentation files served by MkDocs

### Documentation Content Updates

**This is NOT about reference material or documentation structure.** This module handles the complete synchronization of documentation files from the remote repository to each individual HomeServer instance.

**How it works:**
- On every update run, the module clones the full documentation repository from GitHub
- It compares the repository's `VERSION` file against the local version
- If versions differ, it performs a **complete content replacement**:
  - Removes all existing documentation files from `/opt/docs/docs/`
  - Copies all files and directories from the repository's `docs/` subdirectory
  - Copies `mkdocs.yml` configuration file
  - Copies `VERSION` file for tracking
  - Sets proper file ownership and permissions
- If any file or directory fails to copy, the update fails and logs the error

**Key Points:**
- The module pulls the **entire repository** on every update (not incremental)
- It performs a **full replacement** of local docs with repo content (not a merge)
- Missing files/directories in the repo will be removed from local (complete sync)
- All directories and files from `docs/` are copied, including new ones like `reference/`
- The update only runs if the repository `VERSION` differs from local version

**Repository:**
- URL: `https://github.com/homeserversltd/documentation.git`
- Local path: `/opt/docs/docs/`
- Version tracking: `/opt/docs/VERSION` and `/opt/docs/.docs_version`

## Workflow Diagram

```mermaid
flowchart TD
    A[Module Entry] --> B{Command Line Args?}
    
    B -->|--check| C[Check Mode: Status Report]
    B -->|No Args| D[Update Mode: Full Update]
    
    C --> C1[Check Version Updates Needed]
    C1 --> C2[Get Installation Status]
    C2 --> C3[Return Status Report]
    
    D --> E[Check Version Updates Needed]
    E --> F{Any Updates Required?}
    
    F -->|No| G[Skip - All Components Current]
    F -->|Yes| H[Create Backup]
    
    H --> I[Initialize State Manager]
    I --> J[Backup Module State]
    J --> K[Stop MkDocs Service]
    
    K --> L{Software Update Needed?}
    
    L -->|Yes| M[Update MkDocs via pip]
    L -->|No| N[Skip Software Update]
    
    M --> O[Update Material Theme via pip]
    N --> O
    
    O --> P{Documentation Update Needed?}
    
    P -->|Yes| Q[Clone Docs Repository]
    P -->|No| R[Skip Documentation Update]
    
    Q --> S[Deploy New Content]
    S --> T[Set Proper Ownership]
    T --> U[Save New Versions]
    
    R --> U
    
    U --> V[Restore Permissions]
    V --> W[Start MkDocs Service]
    W --> X[Wait for Service Start]
    X --> Y[Verify Installation]
    
    Y --> Z{Verification Passed?}
    
    Z -->|No| AA[Verification Failed]
    Z -->|Yes| BB[Update Complete]
    
    AA --> CC[Rollback from Backup]
    CC --> DD[Restore Module State]
    DD --> EE[Start Service After Rollback]
    EE --> FF[Return Rollback Status]
    
    G --> GG[Return: No Update Needed]
    BB --> HH[Return: Success Status]
    
    style A fill:#e1f5fe
    style HH fill:#c8e6c9
    style G fill:#c8e6c9
    style C3 fill:#c8e6c9
    style FF fill:#ffcdd2
``` 