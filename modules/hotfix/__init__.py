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
Hotfix Module - Universal Emergency Patch Management System

This module provides a powerful, flexible hotfix system that can target any component
in the HOMESERVER system with intelligent version checking and script execution.

Key Features:
- Universal targeting: Can fix any software, module, or system component
- Flexible version checking: Supports module schemas, binary versions, file existence
- Script-based execution: Simple shell scripts in src/ directory
- Intelligent conditions: Only runs when version conditions are met
- StateManager integration: Reliable backup and restore capabilities

Version Check Types:
- module_schema: Check module schema version against max_version
- binary_version: Check binary version using --version flag
- file_exists: Check if file exists (with invert option)
- always: Always run (for universal fixes)

Components:
- HotfixManager: Main target orchestration and execution
- Version checking: Flexible condition evaluation
- Script execution: Direct shell script execution from src/
"""

import os
from pathlib import Path
from .index import HotfixManager, HotfixOperationError, main

__all__ = [
    'HotfixManager',
    'HotfixOperationError', 
    'main'
]
