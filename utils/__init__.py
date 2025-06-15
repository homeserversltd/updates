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
Utilities for the updates orchestration system.

This module provides common utilities used by various update modules.
"""

from .index import log_message, get_module_version
from .version_control import checkout_module_version, list_module_versions, checkout_last_safe
from .state_manager import StateManager

__all__ = [
    'log_message',
    'get_module_version',
    'checkout_module_version',
    'list_module_versions', 
    'checkout_last_safe',
    'StateManager'
]
