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
Hotfix Module - Pool-Based Emergency Patch Management System

This module provides a simplified, robust hotfix system with pool-based operations
and StateManager integration for reliable backup and rollback capabilities.

Key Features:
- Pool-based transactions: Related files grouped together with shared closure commands
- StateManager integration: Leverages existing backup/restore infrastructure
- Graceful failure handling: Failed pools don't break the system
- Customer-first approach: Respects customer modifications through closure validation
- finalClosure support: System-wide validation after all pools complete

Components:
- HotfixManager: Main pool orchestration and execution
- Pool-based operations: Atomic file replacement groups
- StateManager integration: Reliable backup and restore
"""

import os
from pathlib import Path
from .index import HotfixManager, HotfixOperationError, main

__all__ = [
    'HotfixManager',
    'HotfixOperationError', 
    'main'
]
