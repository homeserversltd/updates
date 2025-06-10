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
Hotfix Module - Emergency Patch Management System

This module provides comprehensive hotfix capabilities with advanced rollback
and dependency management for critical system patches.

Key Features:
- Phase-based operation execution with dependency resolution
- Comprehensive rollback capabilities including one-way operations
- State capture and restoration for complex system changes
- Atomic operation groups with checkpoint recovery

Components:
- HotfixManager: Main orchestration and execution
- RollbackManager: Advanced rollback and state restoration
- StateCapture: System state snapshots and recovery points
"""

from .index import HotfixManager, HotfixOperationError, main
from .rollback import RollbackManager, StateCapture, RollbackError

__all__ = [
    'HotfixManager',
    'HotfixOperationError', 
    'RollbackManager',
    'StateCapture',
    'RollbackError',
    'main'
]

__version__ = "1.0.0"
