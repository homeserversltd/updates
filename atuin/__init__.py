"""
Atuin Update Module

Handles update logic specific to the Atuin service.
Implements a main(args) entrypoint for orchestrated updates.
"""
# Import common functionality from parent package
from initialization.files.user_local_lib.updates import log_message, run_update

# Re-export main function from index
from .index import main

# Make functions available at the module level
__all__ = ['main', 'log_message']

# This allows the module to be run directly
if __name__ == "__main__":
    import sys
    main(sys.argv[1:] if len(sys.argv) > 1 else []) 