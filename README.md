# Updates Orchestrator System

## Overview

This directory implements a modular, manifest-driven Python update orchestration system for managing and updating services and components in a robust, maintainable, and extensible way. Updates are run from a single entrypoint, with each update module being self-contained and responsible for its own logic and integrity.

## Key Features

- **Manifest-driven:**  
  All updates, their relationships, and metadata (version, checksum, enablement, etc.) are defined in `manifest.json`. This file is the single source of truth for update orchestration.

- **Python modules:**  
  Each update is a Python module (with an `index.py` and optional `__init__.py`), supporting complex logic, error handling, and integration with Python's ecosystem.

- **Checksum-based integrity:**  
  Each module directory contains a `checksum` file (SHA-256, auto-generated) and exposes a `CHECKSUM` variable for runtime verification against the manifest.

- **Self-contained submodules:**  
  The orchestrator only calls the top-level children defined in the manifest. Each submodule is responsible for invoking its own children, ensuring a failure in one module does not halt the entire process.

- **Robust error handling:**  
  If a submodule fails, the error is logged, but the orchestrator continues with the next update, maximizing the chance that as many updates as possible succeed.

- **Extensible:**  
  New update modules can be added by creating a new subdirectory with the required files and updating the manifest. No changes to the orchestrator are required.

- **Shared utilities:**  
  Common logging, checksum, and helper functions are available in the `utils/` directory.

- **Virtual Environment Isolation:**  
  Dependencies are isolated in a virtual environment to prevent conflicts with system packages.

## Setup

### Virtual Environment Setup

The updates system uses a virtual environment to isolate its dependencies:

```bash
# Run the setup script to create and configure the virtual environment
sudo ./setup_venv.sh

# Or manually:
python3 -m venv /usr/local/lib/user_local_lib/updates/venv
source /usr/local/lib/user_local_lib/updates/venv/bin/activate
pip install -r requirements.txt
```

### Running Updates

```bash
# Using the virtual environment
/usr/local/lib/user_local_lib/updates/venv/bin/python /usr/local/lib/user_local_lib/updates/index.py

# Or activate first
source /usr/local/lib/user_local_lib/updates/venv/bin/activate
python /usr/local/lib/user_local_lib/updates/index.py
```

## Directory Structure

- `manifest.json`  
  The manifest file describing all update modules, their arguments, metadata, and child relationships.

- `index.py`  
  The master orchestrator script. Reads the manifest, verifies checksums, and runs the top-level updates.

- `requirements.txt`  
  Python dependencies for the updates system.

- `setup_venv.sh`  
  Script to set up the virtual environment and install dependencies.

- `venv/`  
  Virtual environment directory (created by setup script).

- `<module_name>/`  
  Each update module is a subdirectory with:
  - `index.py` (required): Contains a `main(args)` function.
  - `__init__.py` (optional but recommended): Exposes `CHECKSUM` and/or `main`.
  - `checksum` (required): SHA-256 hash of the module directory, for integrity verification.
  - `README.md`, `requirements.txt`, `test_*.py` (optional): For documentation, dependencies, and tests.

- `utils/`  
  Shared utilities for logging, checksum calculation, and automation (e.g., `checksummer.py`).

- `config/`  
  Shared shell utilities and configuration scripts.

- `update_*.sh`  
  Legacy or supplementary shell scripts for updates (not required for Python modules).

## Example manifest.json

```json
{
  "updates": [
    {
      "name": "adblock",
      "version": "1.0.0",
      "lastSafeVersion": "1.0.0",
      "lastApplied": "2024-06-10T15:23:00Z",
      "enabled": true,
      "description": "Blocks ads at the network level."
    },
    {
      "name": "all_services",
      "checksum": null,
      "lastApplied": null,
      "lastSafeVersion": null,
      "enabled": true,
      "description": null,
      "children": [
        "adblock",
        "atuin",
        "filebrowser",
        "gogs"
      ]
    }
  ],
  "entrypoint": "all_services"
}
```

## How it Works

- The orchestrator (`index.py`) reads `manifest.json` and runs each child of the entrypoint.
- Each update module (e.g., `adblock/index.py`) implements a `main(args)` function and is responsible for running its own children (if any).
- Before running, the orchestrator verifies the module's checksum against the manifest.
- If a module fails, the error is logged, but the orchestrator continues with the next module.
- This design ensures updates are modular, maintainable, and robust against partial failures.

## Adding a New Update Module

1. Create a new subdirectory under `updates/` (e.g., `foobar/`).
2. Add an `index.py` with a `main(args)` function.
3. Add a `checksum` file (use `utils/checksummer.py` to generate).
4. (Recommended) Add an `__init__.py` that exposes `CHECKSUM` and/or `main`.
5. Add an entry for your module in `manifest.json`, and add it as a child to the appropriate parent.
6. (Optional) Add `README.md`, `requirements.txt`, and tests as needed.

## Example index.py for a Module

```python
def main(args=None):
    print("Running update for this module...")
    # Module-specific update logic here
```

## Example __init__.py for a Module

```python
import os
from ..utils.index import compute_folder_sha256

_CHECKSUM_FILE = os.path.join(os.path.dirname(__file__), "checksum")

def _read_checksum():
    try:
        with open(_CHECKSUM_FILE, "r") as f:
            return f.read().strip()
    except Exception:
        return None

CHECKSUM = _read_checksum()
LIVE_CHECKSUM = compute_folder_sha256(os.path.dirname(os.path.abspath(__file__)))
```

## Best Practices

- Keep each module self-contained and idempotent.
- Handle errors within each module and log them appropriately.
- Only the master orchestrator should run top-level updates; submodules handle their own children.
- Use the manifest as the single source of truth for update relationships and metadata.
- Use the checksummer utility to keep checksums up to date.
- Always use the virtual environment when running updates.

## Version Control and Rollback

The system provides built-in version rollback capabilities using Git tags and the manifest's version tracking.

### Version Tracking
Each module in the manifest includes version information:
```json
{
  "name": "adblock",
  "version": "1.0.0",
  "lastSafeVersion": "1.0.0",
  "lastApplied": "2024-06-10T15:23:00Z",
  "enabled": true
}
```

### Git Tag Convention
Updates are tagged in Git using the format:
```
<module_name>-v<version>-<timestamp>
# Example: adblock-v1.0.0-20240610
```

### Rollback Functions
The `utils.rollback` module provides several functions for version management:

1. **Roll Back to Last Safe Version**
```python
from initialization.files.user_local_lib.updates.utils import rollback_to_last_safe

success = rollback_to_last_safe('adblock')
```

2. **Roll Back to Specific Version**
```python
from initialization.files.user_local_lib.updates.utils import rollback_module

success = rollback_module('adblock', target_version='1.0.0')
```

3. **List Available Versions**
```python
from initialization.files.user_local_lib.updates.utils import list_available_versions

versions = list_available_versions('adblock')
for v in versions:
    print(f"Version {v['version']} from {v['timestamp']}")
```

### Deployment Best Practices

1. **Tag Updates When Deploying**
```bash
# After successful update
git tag adblock-v1.0.0-$(date +%Y%m%d) HEAD
git push origin adblock-v1.0.0-$(date +%Y%m%d)
```

2. **Update Manifest Fields**
- `version`: Set to new version when deploying
- `lastSafeVersion`: Update when version is confirmed stable
- `lastApplied`: Set to deployment timestamp
- `enabled`: Toggle module activation

3. **Rollback Safety**
- Test rollbacks in staging environment first
- Keep Git tags synchronized across environments
- Document configuration changes with versions
- Create pre-rollback backups when possible
- Verify rolled-back version functionality

## Utilities

- `utils/index.py`: Logging and checksum helpers.
- `utils/checksummer.py`: Script to (re)generate checksums for all modules.
- `utils/rollback.py`: Version rollback and management utilities.
- `config/utils.sh`: Shared shell functions for update scripts.

## Dependencies

The updates system requires the following Python packages:
- `requests`: For HTTP requests (used by adblock module)
- `pathlib2`: For Python < 3.4 compatibility (if needed)

All dependencies are managed through the virtual environment to ensure isolation from system packages.

## License

This system is intended for internal use. Adapt and extend as needed for your environment.