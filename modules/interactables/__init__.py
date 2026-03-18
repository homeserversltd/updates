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

This module is the single source of truth for interactables. Scripts live in
src/; each interactable is defined in this module's index.json under
"interactables" (id, name, description, script, has_run, completion_check,
show_only_if). The Admin backend reads this index and runs scripts from
modules/interactables/src. This module does not run scripts during update
cycles; it provides --check and --version for the orchestrator.
"""

import os
from pathlib import Path
from .index import InteractablesManager, InteractablesModuleError, main

__all__ = [
    "InteractablesManager",
    "InteractablesModuleError",
    "main",
]

