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

This module handles updating the HOMESERVER web interface from the GitHub repository.
It supports selective component updates, automatic rollback on failure, and comprehensive
backup management.

Key Features:
- GitHub repository integration
- Selective component updates (frontend, backend, premium, config, public)
- Automatic backup and rollback capabilities
- npm build process management
- Service restart and health checking
- Configurable update policies per component

Usage:
    from modules.website import WebsiteUpdater
    
    updater = WebsiteUpdater()
    success = updater.update()
"""

from .index import WebsiteUpdater

__all__ = ['WebsiteUpdater']

# Module metadata
__version__ = '1.0.0'
__author__ = 'HOMESERVER Development Team'
__description__ = 'Website update module for HOMESERVER platform'
