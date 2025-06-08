from .index import main
from initialization.files.user_local_lib.updates import log_message
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

__all__ = ['main', 'log_message', 'CHECKSUM', 'LIVE_CHECKSUM']

if __name__ == "__main__":
    import sys
    main(sys.argv[1:] if len(sys.argv) > 1 else [])
