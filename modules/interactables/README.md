# Interactables Module

## Overview

User-triggered one-off actions (interactables) presented in the Admin Updates UI. Scripts live here; the root updates `index.json` defines which are shown and their `script_dir` points at this module's `src/`. Execution is done by the backend (Admin updates utils), not by the update orchestrator.

## Directory Structure

```
interactables/
├── index.json    # Module metadata + list of interactables (id, script, description)
├── index.py      # InteractablesManager; main() for --check / --version
├── __init__.py   # Public API
├── README.md
└── src/          # Scripts run by Admin UI (script_dir in root index)
    ├── 10000000.sh
    └── debian12_to_13.sh
```

## Core Components

- **InteractablesManager**: Loads `index.json`, lists scripts in `src/`, provides `check()` and script presence.
- **main(args)**: Entry for orchestrator; supports `--check` and `--version`. No run path; scripts are run only via Admin UI.

## Integration

- **Root index** (`/usr/local/lib/updates/index.json`): `interactives[]` entries reference `script_dir: "modules/interactables/src"` and `script: "<name>.sh"`. Backend builds path as `UPDATES_ROOT / script_dir / script`.
- **Backend**: `backend/admin/updates/utils.py` — `get_interactives()`, `run_interactive(id)`; reads root index, runs script at resolved path, marks `has_run` in root index.
- **Orchestrator**: May call `run_update("modules.interactables", ["--check"])` for status; does not execute interactables during update cycles.

## Configuration

| Item | Location | Purpose |
|------|----------|---------|
| Module metadata | `interactables/index.json` → `metadata` | schema_version, description, enabled, priority |
| Interactable list (module) | `interactables/index.json` → `interactables` | id, script, description (self-describing) |
| UI list + script_dir | Root `index.json` → `interactives` | name, description, script, script_dir, has_run, completion_check, show_only_if |

## Adding an Interactable

1. Add script to `src/<id>.sh` (or `<name>.sh`); make executable.
2. Add entry to this module's `index.json` under `interactables`: `id`, `script`, `description`.
3. Add entry to root `index.json` under `interactives`: `id`, `name`, `description`, `script`, `script_dir`: `"modules/interactables/src"`, `has_run`: false; optionally `completion_check` or `show_only_if`.

Script path used at run time is `UPDATES_ROOT/modules/interactables/src/<script>`.

## Troubleshooting

- **Script not found**: Ensure `script_dir` in root index is `modules/interactables/src` and script exists in `src/`.
- **Module check**: From updates root, `python3 -c "from updates.modules.interactables import main; print(main(['--check']))"` (or run update manager with interactables enabled and check phase).
