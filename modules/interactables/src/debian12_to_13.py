#!/usr/bin/python3
"""
Entry point for Debian 12 → 13 in-place upgrade (fractalization).
Loads the deb12-13 module by path and runs its orchestrator. No shell; straight-line path.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def main() -> int:
    script_dir = Path(__file__).resolve().parent
    module_dir = script_dir / "deb12-13"
    index_py = module_dir / "index.py"
    if not index_py.is_file():
        print("debian12_to_13: deb12-13/index.py not found", file=sys.stderr)
        return 1
    spec = importlib.util.spec_from_file_location("deb12_13_index", index_py)
    if spec is None or spec.loader is None:
        print("debian12_to_13: failed to load deb12-13 module", file=sys.stderr)
        return 1
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.main(module_path=module_dir)


if __name__ == "__main__":
    sys.exit(main())
