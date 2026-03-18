"""
HOMESERVER Update Management System - Interactables Module
Copyright (C) 2024 HOMESERVER LLC

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

"""
Interactables Module - User-triggered one-off actions

This module holds scripts that are presented in the Admin Updates UI as
interactables (e.g. "Migrate Gogs to Forgejo", "Debian 12 to 13 upgrade").
Execution is triggered by the user from the UI; the backend runs the script
using script_dir from the root updates index.json (modules/interactables/src).

Key points:
- Scripts live in src/; each interactable is defined in root index.json
  under "interactives" with script_dir "modules/interactables/src".
- This module does not run scripts during update cycles; it provides
  --check and --version for the orchestrator and documents the set of
  interactables in index.json.
"""

import os
from pathlib import Path
from .index import InteractablesManager, InteractablesModuleError, main

__all__ = [
    "InteractablesManager",
    "InteractablesModuleError",
    "main",
]

