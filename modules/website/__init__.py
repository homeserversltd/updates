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
HOMESERVER Website Update Module

This module handles updating the HOMESERVER web interface from the GitHub repository
with StateManager integration for reliable backup and rollback capabilities.

Key Features:
- GitHub repository integration with shallow cloning
- Component-based updates (frontend, backend, premium, public, config)
- StateManager integration for reliable backup and restore
- Graceful failure handling with automatic rollback
- npm build process management with service restart validation
- Customer-first approach: failed updates don't break existing installations

Components:
- WebsiteUpdater: Main git-based updater with StateManager integration
- Automatic backup before updates
- Graceful rollback on any failure (clone, copy, build, or service restart)
- Simple failure reporting for orchestrator

Usage:
    from modules.website import WebsiteUpdater
    
    updater = WebsiteUpdater()
    result = updater.update()
    if result["success"]:
        print("Website updated successfully")
    else:
        print(f"Update failed: {result['message']}")
"""

import json
import os
from pathlib import Path

from .index import WebsiteUpdater, main
from updates.utils.index import get_module_version

__version__ = get_module_version(os.path.dirname(os.path.abspath(__file__)))
__all__ = ['WebsiteUpdater', 'main']
