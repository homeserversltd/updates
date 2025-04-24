"""
Atuin Update Module

Handles update logic specific to the Atuin service.
Implements a main(args) entrypoint for orchestrated updates.
"""
# Import common functionality from parent package
from initialization.files.user_local_lib.updates import log_message, run_update
from .index import main

# Expose CHECKSUM for orchestrator integrity checks
import os
from ..utils.index import compute_folder_sha256

_CHECKSUM_FILE = os.path.join(os.path.dirname(__file__), "checksum")

def _read_checksum():
    try:
        with open(_CHECKSUM_FILE, "r") as f:
            return f.read().strip()
    except Exception:
        return None

CHECKSUM = _read_checksum()
LIVE_CHECKSUM = compute_folder_sha256(os.path.dirname(os.path.abspath(__file__)))

# Make functions available at the module level
__all__ = ['main', 'log_message', 'CHECKSUM', 'LIVE_CHECKSUM']

# This allows the module to be run directly
if __name__ == "__main__":
    import sys
    main(sys.argv[1:] if len(sys.argv) > 1 else []) 