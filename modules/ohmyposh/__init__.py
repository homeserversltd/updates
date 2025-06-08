from .index import main
from ...index import log_message

__all__ = ['main', 'log_message']

if __name__ == "__main__":
    import sys
    main(sys.argv[1:] if len(sys.argv) > 1 else [])
