"""
HOMESERVER Update Management System - Migrations Module
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
Migrations Module - One-Time System Evolution Management

This module provides controlled execution of one-time system-wide changes across
all HOMESERVER installations with sequential ordering and automatic retry.

Key Features:
- Sequential execution: Migrations run in strict numerical order from index.json
- Automatic retry: Failed migrations retry on next update cycle
- Idempotent design: All migrations must be safe to run multiple times
- State tracking: Tracks completion via has_run flags in index.json
- Comprehensive logging: Full visibility into migration execution

Migration Numbering:
- 00000001-09999999: System infrastructure migrations
- 10000000-19999999: Service migrations  
- 20000000-29999999: Database schema migrations
- 30000000-39999999: Configuration migrations
- 40000000-49999999: Security updates
- 50000000-99999999: Reserved for future use

Components:
- MigrationManager: Sequential migration orchestration and state tracking
- Script execution: Bash scripts in src/ directory named by migration ID
- Automatic retry: Failed migrations leave has_run=false for next attempt
"""

import os
from pathlib import Path
from .index import MigrationManager, MigrationError, main

__all__ = [
    'MigrationManager',
    'MigrationError',
    'main'
]

__version__ = "1.0.0"

