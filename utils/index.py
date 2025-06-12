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

import datetime
import sys
import hashlib
import os
import json
from pathlib import Path

def log_message(message, level="INFO"):
    """
    Log a message with a timestamp and level to stdout.
    Args:
        message (str): The message to log.
        level (str): Log level (e.g., 'INFO', 'ERROR').
    """
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}", file=sys.stdout)

def get_module_version(module_path: str) -> str:
    """
    Get the schema version from a module's index.json file.
    
    Args:
        module_path (str): Path to the module directory
        
    Returns:
        str: The schema version from index.json, or "unknown" if not found
    """
    try:
        index_path = Path(module_path) / "index.json"
        with open(index_path, 'r') as f:
            config = json.load(f)
            return config.get("metadata", {}).get("schema_version", "unknown")
    except Exception as e:
        log_message(f"Failed to read module version from {module_path}: {e}", "ERROR")
        return "unknown"

