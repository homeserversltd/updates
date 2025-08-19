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
Common utilities for update modules to reduce code duplication.

This module provides shared functionality used across multiple update modules.
"""

import os
import json
from updates.index import log_message


def load_root_config():
    """
    Load the root index.json to check debug settings.
    
    This function navigates from any module directory to the root updates
    directory and loads the debug configuration.
    
    Returns:
        dict: Root configuration with debug flag, or default {"debug": False} if loading fails
    """
    try:
        # Navigate to the root updates directory from utils location
        # Utils is at: /usr/local/lib/updates/utils/
        # Root config is at: /usr/local/lib/updates/index.json
        # So we only need to go up ONE directory, not two
        root_config_path = os.path.join(os.path.dirname(__file__), "..", "index.json")
        with open(root_config_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        log_message(f"Failed to load root config: {e}", "DEBUG")
        # Default to non-debug mode for production safety
        return {"debug": False}


def conditional_config_return(result_dict: dict, config_data: dict, debug_key: str = "debug") -> dict:
    """
    Conditionally add config to result based on debug flag.
    
    This utility function checks the root debug flag and conditionally
    includes configuration data in the result dictionary.
    
    Args:
        result_dict: The result dictionary to potentially add config to
        config_data: The configuration data to add if debug is enabled
        debug_key: The key to check in root config (default: "debug")
        
    Returns:
        dict: Result dictionary with config added if debug is enabled
    """
    root_config = load_root_config()
    if root_config.get(debug_key, False):
        result_dict["config"] = config_data
    return result_dict


def get_module_debug_mode() -> bool:
    """
    Get the current debug mode from root configuration.
    
    Returns:
        bool: True if debug mode is enabled, False otherwise
    """
    root_config = load_root_config()
    return root_config.get("debug", False)
