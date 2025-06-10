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
Adblock Update Module

Handles update logic specific to the Adblock service.
Implements a main(args) entrypoint for orchestrated updates.
"""

import os
from ..utils.index import compute_folder_sha256
from .index import main  # Expose main at package level

# Path to the checksum file (relative to this __init__.py)
_CHECKSUM_FILE = os.path.join(os.path.dirname(__file__), "checksum")


def _read_checksum():
    """Read the SHA-256 checksum from the checksum file (written by the checksummer utility)."""
    try:
        with open(_CHECKSUM_FILE, "r") as f:
            return f.read().strip()
    except Exception:
        return None

# The checksum as written by the checksummer utility (should match manifest)
CHECKSUM = _read_checksum()

# The live-computed checksum of the module folder (for integrity verification)
LIVE_CHECKSUM = compute_folder_sha256(os.path.dirname(os.path.abspath(__file__))) 