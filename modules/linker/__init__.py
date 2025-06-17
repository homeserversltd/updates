"""
HOMESERVER Update Management System
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
HOMESERVER Linker Update Module

This module handles updating the HOMESERVER linker script suite from the GitHub repository
with StateManager integration for reliable backup and rollback capabilities.

Key Features:
- GitHub repository integration with shallow cloning
- Component-based updates (scripts and config)
- StateManager integration for reliable backup and restore
- Graceful failure handling with automatic rollback
- Permission preservation during updates
- Customer-first approach: failed updates don't break existing installations

Components:
- LinkerUpdater: Main git-based updater with StateManager integration
- Automatic backup before updates
- Graceful rollback on any failure (clone, copy, or permission issues)
- Simple failure reporting for orchestrator

Usage:
    from modules.linker import LinkerUpdater
    
    updater = LinkerUpdater()
    result = updater.update()
    if result["success"]:
        print("Linker scripts updated successfully")
    else:
        print(f"Update failed: {result['message']}")
"""

import json
import os
from pathlib import Path

from .index import LinkerUpdater, main

__all__ = ['LinkerUpdater', 'main'] 