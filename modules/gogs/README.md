# Gogs Update Module

## Binary URL and fallback (why updates failed on 0.14+)

GitHub release asset **file names changed** between 0.13.x and 0.14.x:

| Release | Example asset name |
|--------|---------------------|
| 0.13.3 | `gogs_0.13.3_linux_amd64.tar.gz` |
| 0.14.2 | `gogs_v0.14.2_linux_amd64.tar.gz` |

A single `binary_download_url_template` using `gogs_{version}_linux_amd64.tar.gz` matches 0.13.x but **404s on 0.14.x** (missing the extra `v` in the archive name).

**Resolution in code:** `resolve_gogs_linux_amd64_tarball_url()` loads the release’s `assets` from the GitHub API and picks the `linux_amd64` `.tar.gz`. If the API is unavailable, it probes two known URL patterns with `HEAD`.

**Source fallback:** Upstream removed the old `Makefile` `build` target; 0.14 uses `go build` (see `Taskfile.yml`). The module now runs `go build` and reuses the same **data-preserving** swap as the tarball path. Older distro Go versions may still fail if below Gogs’ `go.mod` requirement; prefer the binary path.

**Forgejo:** If the host is migrated to Forgejo, `detect_git_server()` skips this module.

## Workflow Diagram

```mermaid
flowchart TD
    A[Module Entry] --> B{Command Line Args?}
    
    B -->|Yes| C[Handle CLI Commands]
    B -->|No| D[Start Update Process]
    
    C --> C1[--version: Version Check]
    C --> C2[--check: Simple Status]
    C --> C3[--verify: Full Verification]
    C --> C4[--config: Show Config]
    C --> C5[--fix-permissions: Restore Perms]
    
    D --> E[Get Current Version]
    E --> F[Get Latest Version]
    F --> G{Update Needed?}
    
    G -->|No| H[Skip - Already Current]
    G -->|Yes| I[Create Backup]
    
    I --> J[Initialize State Manager]
    J --> K[Backup Module State]
    K --> L{Backup Success?}
    
    L -->|No| M[Return Error]
    L -->|Yes| N[Install Update]
    
    N --> O[Try Binary Installation]
    O --> P{Binary Success?}
    
    P -->|Yes| Q[Restore Permissions]
    P -->|No| R[Fallback to Source]
    
    R --> S[Clone Source Repository]
    S --> T[Build from Source]
    T --> U{Source Success?}
    
    U -->|No| V[Both Methods Failed]
    U -->|Yes| Q
    
    Q --> W[Verify Installation]
    W --> X{Verification Passed?}
    
    X -->|No| Y[Rollback from Backup]
    X -->|Yes| Z[Update Complete]
    
    Y --> AA[Restore Module State]
    AA --> BB[Return Rollback Status]
    
    H --> CC[Return Current Status]
    Z --> DD[Return Success Status]
    
    style A fill:#e1f5fe
    style Z fill:#c8e6c9
    style M fill:#ffcdd2
    style V fill:#ffcdd2
    style Y fill:#ffcdd2
``` 