"""
Adblock Update Module

Handles update logic specific to the Adblock service.
Implements a main(args) entrypoint for orchestrated updates.
"""
# from .index import main  # Uncomment if you want to expose main at the package level 

import os
from ..utils.index import compute_folder_sha256

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