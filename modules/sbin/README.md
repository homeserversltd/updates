# sbin Module

Purpose: Manage `/usr/local/sbin` scripts as first-class, open-source artifacts.

Behavior:
- Compare destination file sha256 and permissions to manifest
- If drift is detected, atomically replace from `src/` and enforce owner/mode
- Optional `skipIfLocal: true` skips files containing `# HS_UPDATE: local`

Manifest fields:
- `source`: filename in `src/`
- `destination`: absolute install path
- `sha256`: expected content hash of source (empty allowed; computed at runtime)
- `owner`/`group`/`mode`: enforced permissions
- `skipIfLocal`: honor local override marker

Check mode:
- Reports content/permission drift, no changes applied

Apply mode:
- Backup current file via StateManager
- Write temp, set perms, rename atomically
- Report updated items


