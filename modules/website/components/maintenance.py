"""
HOMESERVER Website Update Components
Copyright (C) 2024 HOMESERVER LLC

Maintenance Manager Component

Runs maintenance tasks that are independent of build/deploy, such as
keeping Browserslist's caniuse-lite database up to date. This must not
be tied to the build pipeline and should run on every module invocation
where appropriate.
"""

import subprocess
from typing import Dict, Any

from updates.index import log_message


class MaintenanceManager:
    """Handles maintenance tasks that are agnostic of building."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.base_dir = (
            config.get("config", {})
            .get("target_paths", {})
            .get("base_directory", "/var/www/homeserver")
        )

    def update_browserslist(self) -> bool:
        """
        Update Browserslist database using npx, regardless of whether a build
        is being performed. This is intentionally separate from the build flow.

        Returns:
            bool: True if the update command executed successfully, False otherwise
        """
        log_message("[MAINT] Updating Browserslist DB via npx…")
        try:
            # Use --yes to avoid interactive prompts; run from the project root
            result = subprocess.run(
                ["npx", "--yes", "update-browserslist-db@latest"],
                cwd=self.base_dir,
                capture_output=True,
                text=True,
                timeout=180,
            )

            if result.returncode != 0:
                log_message(
                    f"[MAINT] ✗ Browserslist DB update failed: {result.stderr}", "WARNING"
                )
                return False

            # Log a succinct tail of output for traceability
            if result.stdout:
                lines = result.stdout.strip().split("\n")
                log_message(f"[MAINT] Browserslist update output ({len(lines)} lines):")
                for line in lines[-5:]:
                    log_message(f"[MAINT]   {line}")

            log_message("[MAINT] ✓ Browserslist DB updated successfully")
            return True

        except subprocess.TimeoutExpired:
            log_message("[MAINT] ✗ Browserslist DB update timed out", "WARNING")
            return False
        except Exception as e:
            log_message(f"[MAINT] ✗ Browserslist DB update error: {e}", "WARNING")
            return False


