"""
HOMESERVER Update Management System - Interactables Module
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

import os
import json
import logging
from pathlib import Path
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


def _log(message: str, level: str = "INFO") -> None:
    """Log to module logger; orchestrator may attach handlers."""
    if level == "ERROR":
        logger.error(message)
    elif level == "WARNING":
        logger.warning(message)
    else:
        logger.info(message)


class InteractablesModuleError(Exception):
    """Raised when interactables module config or structure is invalid."""
    pass


class InteractablesManager:
    """
    Interactables module: metadata and script listing only.
    Execution is performed by the Admin backend (utils.run_interactive) using
    script_dir from the root index.json interactives array.
    """

    def __init__(self, module_path: str) -> None:
        self.module_path = Path(module_path)
        self.index_file = self.module_path / "index.json"
        self.config = self._load_config()
        self.src_dir = self.module_path / "src"

    def _load_config(self) -> Dict[str, Any]:
        """Load module index.json."""
        try:
            with open(self.index_file, "r") as f:
                return json.load(f)
        except Exception as e:
            _log(f"Failed to load interactables config: {e}", "ERROR")
            return {}

    def list_scripts(self) -> List[Dict[str, Any]]:
        """Return list of interactable entries with script presence in src/."""
        entries = self.config.get("interactables", [])
        result = []
        for entry in entries:
            script_name = entry.get("script", "")
            script_path = self.src_dir / script_name
            result.append({
                "id": entry.get("id", ""),
                "script": script_name,
                "description": entry.get("description", ""),
                "present": script_path.is_file(),
            })
        return result

    def check(self) -> Dict[str, Any]:
        """Status of the interactables module (scripts present, schema version)."""
        scripts = self.list_scripts()
        metadata = self.config.get("metadata", {})
        return {
            "success": True,
            "schema_version": metadata.get("schema_version", "unknown"),
            "description": metadata.get("description", ""),
            "interactables_count": len(scripts),
            "scripts": scripts,
        }


def main(args: Any = None) -> Dict[str, Any]:
    """
    Entry point for the interactables module.
    Supports --check and --version. No run path; execution is via Admin UI backend.
    """
    if args is None:
        args = []
    module_path = os.path.dirname(os.path.abspath(__file__))
    try:
        manager = InteractablesManager(module_path)
        if "--check" in args:
            result = manager.check()
            _log(
                f"Interactables module: {result['interactables_count']} interactables, "
                f"schema {result['schema_version']}"
            )
            return result
        if "--version" in args:
            metadata = manager.config.get("metadata", {})
            schema_version = metadata.get("schema_version", "unknown")
            _log(f"Interactables module version: {schema_version}")
            return {
                "success": True,
                "schema_version": schema_version,
                "module": "interactables",
            }
        # Default: same as --check
        return manager.check()
    except Exception as e:
        _log(f"Interactables module failed: {e}", "ERROR")
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    import sys
    result = main(sys.argv[1:])
    if not result.get("success", False):
        sys.exit(1)
