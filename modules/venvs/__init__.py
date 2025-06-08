from .index import main

__all__ = ['main']

if __name__ == "__main__":
    import sys
    main(sys.argv[1:] if len(sys.argv) > 1 else [])
