# Interactables Module

## Overview

User-triggered one-off actions (interactables) presented in the Admin Updates UI. This module is the **single source of truth**: `index.json` defines the list (id, name, description, script, has_run, completion_check, show_only_if). Scripts live in `src/`. The backend reads this module's index and runs scripts from `modules/interactables/src`. Execution is done by the backend (Admin updates utils), not by the update orchestrator.

## Directory Structure

```
interactables/
├── index.json    # Module metadata + interactables[] (full schema)
├── index.py      # InteractablesManager; main() for --check / --version
├── __init__.py   # Public API
├── README.md
└── src/          # Scripts run by Admin UI
    ├── debian12_to_13.py   # Entry point (fractalization); loads deb12-13/
    ├── deb12-13/           # Debian 12→13 module (infinite-index)
    │   ├── index.json
    │   ├── index.py
    │   ├── kea_dhcp4_add_subnet_id.py
    │   └── README.md
    ├── gogs_to_forgejo.sh
    ├── postgres15_to_17.sh
    └── php_fpm_migrate.sh
```

## Core Components

- **InteractablesManager**: Loads `index.json`, lists scripts in `src/`, provides `check()` and script presence.
- **main(args)**: Entry for orchestrator; supports `--check` and `--version`. No run path; scripts are run only via Admin UI.

## Integration

- **Module index** (`/usr/local/lib/updates/modules/interactables/index.json`): `interactables[]` with id, name, description, script, has_run, completion_check, show_only_if. Script path is always `UPDATES_ROOT/modules/interactables/src/<script>`.
- **Backend**: `backend/admin/updates/utils.py` — `get_interactives()`, `run_interactive(id)`; reads and writes this module's index only; runs script at fixed path; marks `has_run` in this index.
- **Orchestrator**: May call `run_update("modules.interactables", ["--check"])` for status; does not execute interactables during update cycles.

## Configuration

| Item | Location | Purpose |
|------|----------|---------|
| Module metadata | `interactables/index.json` → `metadata` | schema_version, description, enabled, priority |
| Interactable list | `interactables/index.json` → `interactables` | id, name, description, script, has_run, completion_check, show_only_if |

## Adding an Interactable

1. Add script to `src/<name>.sh` or `src/<name>.py`; make executable if shell.
2. Add entry to this module's `index.json` under `interactables`: `id`, `name`, `description`, `script`, `has_run`: false; optionally `completion_check` or `show_only_if`.

Script path at run time is `UPDATES_ROOT/modules/interactables/src/<script>`. Backend runs `.py` with `python3`, `.sh` with `bash`.

## Troubleshooting

- **Script not found**: Ensure script exists in `src/` and `script` in `interactables[]` matches the filename.
- **Module check**: From updates root, `python3 -c "from updates.modules.interactables import main; print(main(['--check']))"` (or run update manager with interactables enabled and check phase).
