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
