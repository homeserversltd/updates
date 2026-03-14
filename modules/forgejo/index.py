"""
HOMESERVER Update Management System - Forgejo module
Copyright (C) 2024 HOMESERVER LLC

Forgejo Git server update module. Part of the "git" group; only one of gogs/forgejo
runs per update cycle (orchestrator ladder logic). Update flow: binary-only replace
(stop service, backup binary, download from Codeberg, replace, chmod/chown, start).
"""

import os
import json
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from updates.index import log_message
from updates.utils.permissions import PermissionManager, PermissionTarget
from updates.utils.state_manager import StateManager

def load_module_config() -> Dict[str, Any]:
    try:
        config_path = os.path.join(os.path.dirname(__file__), "index.json")
        with open(config_path, "r") as f:
            return json.load(f)
    except Exception as e:
        log_message(f"Failed to load module config: {e}", "WARNING")
        return {
            "metadata": {"module_name": "forgejo", "schema_version": "0.1.0"},
            "config": {
                "directories": {
                    "forgejo_bin": {"path": "/opt/forgejo/forgejo"},
                },
                "permissions": {"owner": "git", "group": "git"},
            },
        }

MODULE_CONFIG = load_module_config()

SERVICE_NAME = "forgejo"
# Codeberg API for Forgejo releases (same structure as manual_deploy.py URL pattern)
CODEBERG_RELEASES_URL = "https://codeberg.org/api/v1/repos/forgejo/forgejo/releases"


def _compare_versions(a: str, b: str) -> int:
    """Compare semantic versions. Returns -1 if a < b, 0 if a == b, 1 if a > b."""
    def parse(v: str) -> Tuple[int, ...]:
        parts = []
        for x in v.strip().split("."):
            try:
                parts.append(int(x))
            except ValueError:
                parts.append(0)
        return tuple(parts) if parts else (0,)
    pa, pb = parse(a), parse(b)
    if pa < pb:
        return -1
    if pa > pb:
        return 1
    return 0


def get_latest_forgejo_version() -> Optional[str]:
    """Get latest Forgejo version from Codeberg API (releases list, first = latest)."""
    try:
        req = urllib.request.Request(CODEBERG_RELEASES_URL)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.load(resp)
        if not data or not isinstance(data, list):
            return None
        tag = data[0].get("tag_name", "")
        if tag.startswith("v"):
            return tag[1:]
        return tag
    except Exception as e:
        log_message(f"Failed to get latest Forgejo version: {e}", "WARNING")
        # Fallback: config or manual_deploy default
        inst = MODULE_CONFIG.get("config", {}).get("installation", {})
        return inst.get("fallback_version", "14.0.2")


def get_forgejo_version() -> Optional[str]:
    """Detect currently installed Forgejo version."""
    try:
        bin_cfg = MODULE_CONFIG["config"]["directories"].get("forgejo_bin", {})
        bin_path = bin_cfg.get("path", "/opt/forgejo/forgejo") if isinstance(bin_cfg, dict) else bin_cfg
        if not os.path.isfile(bin_path) or not os.access(bin_path, os.X_OK):
            return None
        result = subprocess.run(
            [bin_path, "--version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        if result.returncode != 0:
            return None
        # e.g. "Forgejo version 14.0.2" or "Gitea version ..." (Forgejo is a fork)
        parts = result.stdout.strip().split()
        if len(parts) >= 3 and parts[1] == "version":
            return parts[2]
        return None
    except Exception as e:
        log_message(f"Forgejo version detection failed: {e}", "WARNING")
        return None


def restore_forgejo_permissions() -> bool:
    """Restore ownership/permissions for Forgejo paths."""
    try:
        cfg = MODULE_CONFIG["config"]
        owner = cfg.get("permissions", {}).get("owner", "git")
        group = cfg.get("permissions", {}).get("group", "git")
        targets = []
        for key, dir_cfg in cfg.get("directories", {}).items():
            path = dir_cfg.get("path") if isinstance(dir_cfg, dict) else dir_cfg
            if path and os.path.exists(path):
                recursive = os.path.isdir(path)
                targets.append(
                    PermissionTarget(path=path, owner=owner, group=group, mode=0o755, recursive=recursive)
                )
        if not targets:
            return True
        pm = PermissionManager("forgejo")
        return pm.set_permissions(targets)
    except Exception as e:
        log_message(f"Permission restoration failed: {e}", "ERROR")
        return False


def _run(cmd: list, timeout: int = 60) -> bool:
    """Run command; return True if returncode 0."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0
    except Exception as e:
        log_message(f"Command failed: {e}", "WARNING")
        return False


def install_forgejo_binary(version: str) -> Dict[str, Any]:
    """
    Install Forgejo binary only (data-preserving). Mirrors manual_deploy.py download/replace.
    Stop service, backup current binary, download new binary, replace, chmod/chown, start.
    """
    cfg = MODULE_CONFIG["config"]
    inst = cfg.get("installation", {})
    url_template = inst.get("binary_url_template", "https://codeberg.org/forgejo/forgejo/releases/download/v{version}/forgejo-{version}-linux-amd64")
    download_url = url_template.format(version=version)
    bin_cfg = cfg["directories"].get("forgejo_bin", {})
    bin_path = bin_cfg.get("path", "/opt/forgejo/forgejo") if isinstance(bin_cfg, dict) else bin_cfg
    owner = cfg.get("permissions", {}).get("owner", "git")
    group = cfg.get("permissions", {}).get("group", "git")

    log_message(f"Downloading Forgejo {version} from {download_url}")
    try:
        with tempfile.NamedTemporaryFile(prefix="forgejo_", suffix=".bin", delete=False) as tmp:
            tmp_path = tmp.name
        urllib.request.urlretrieve(download_url, tmp_path)
    except Exception as e:
        log_message(f"Download failed: {e}", "ERROR")
        return {"success": False, "error": str(e)}

    if not os.path.isfile(bin_path):
        log_message("Forgejo binary not present; cannot backup", "ERROR")
        os.unlink(tmp_path)
        return {"success": False, "error": "No existing binary to replace"}

    log_message("Stopping forgejo service...")
    if not _run(["systemctl", "stop", "forgejo"], timeout=30):
        log_message("systemctl stop forgejo failed", "WARNING")

    try:
        log_message("Replacing binary...")
        shutil.copy2(tmp_path, bin_path)
        os.chmod(bin_path, 0o755)
        if shutil.which("chown"):
            subprocess.run(["chown", f"{owner}:{group}", bin_path], check=True, timeout=10)
    except Exception as e:
        log_message(f"Replace failed: {e}", "ERROR")
        os.unlink(tmp_path)
        _run(["systemctl", "start", "forgejo"])
        return {"success": False, "error": str(e)}
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    log_message("Starting forgejo service...")
    if not _run(["systemctl", "start", "forgejo"], timeout=30):
        log_message("systemctl start forgejo failed", "ERROR")
        return {"success": False, "error": "Service failed to start after replace"}
    return {"success": True}


def main(args=None):
    """
    Main entry point for Forgejo update module.
    Orchestrator runs this only when Forgejo is the active git implementation (group ladder).
    """
    if args is None:
        args = []

    module_dir = Path(__file__).parent

    if args and len(args) > 0:
        if args[0] == "--version":
            version = get_forgejo_version()
            if version:
                log_message(f"Detected Forgejo version: {version}")
                return {"success": True, "version": version}
            return {"success": False, "error": "Version detection failed"}
        if args[0] == "--fix-permissions":
            log_message("Restoring Forgejo permissions...")
            ok = restore_forgejo_permissions()
            return {"success": ok, "message": "Permissions restored" if ok else "Permission restoration failed"}
        if args[0] == "--config":
            cfg = MODULE_CONFIG["config"].get("directories", {})
            paths = {k: (v.get("path") if isinstance(v, dict) else v) for k, v in cfg.items()}
            log_message("Current Forgejo module configuration:")
            for k, p in paths.items():
                log_message(f"  {k}: {p}")
            return {"success": True, "config": MODULE_CONFIG, "paths": paths}
        if args[0] == "--verify":
            version = get_forgejo_version()
            bin_cfg = MODULE_CONFIG["config"]["directories"].get("forgejo_bin", {})
            bin_path = bin_cfg.get("path", "/opt/forgejo/forgejo") if isinstance(bin_cfg, dict) else bin_cfg
            binary_exists = os.path.isfile(bin_path)
            binary_executable = binary_exists and os.access(bin_path, os.X_OK)
            return {
                "success": bool(version and binary_executable),
                "verification": {
                    "binary_exists": binary_exists,
                    "binary_executable": binary_executable,
                    "version_readable": bool(version),
                },
                "version": version,
            }
        if args[0] == "--check":
            version = get_forgejo_version()
            if version:
                log_message(f"OK - Current version: {version}")
                return {"success": True, "version": version}
            log_message("Forgejo binary not found or not executable", "ERROR")
            return {"success": False, "error": "Not found"}

    log_message("Starting Forgejo module update...")
    current_version = get_forgejo_version()
    if not current_version:
        log_message("Forgejo not installed or binary not runnable; skipping", "WARNING")
        return {"success": True, "skipped": True, "reason": "not_installed"}

    latest_version = get_latest_forgejo_version()
    if not latest_version:
        log_message("Could not determine latest Forgejo version; skipping update", "WARNING")
        restore_forgejo_permissions()
        return {"success": True, "updated": False, "version": current_version}

    if _compare_versions(current_version, latest_version) >= 0:
        log_message(f"Forgejo already at latest version ({current_version})")
        restore_forgejo_permissions()
        return {"success": True, "updated": False, "version": current_version}

    log_message(f"Update available: {current_version} -> {latest_version}")
    bin_cfg = MODULE_CONFIG["config"]["directories"].get("forgejo_bin", {})
    bin_path = bin_cfg.get("path", "/opt/forgejo/forgejo") if isinstance(bin_cfg, dict) else bin_cfg
    state_manager = StateManager()
    backup_ok = state_manager.backup_module_state(
        module_name=SERVICE_NAME,
        description=f"pre_update_{current_version}_to_{latest_version}",
        files=[bin_path],
        services=["forgejo"],
    )
    if not backup_ok:
        log_message("Backup failed; aborting update", "ERROR")
        return {"success": False, "error": "Backup failed"}

    install_result = install_forgejo_binary(latest_version)
    if not install_result.get("success"):
        log_message("Restoring from backup...", "WARNING")
        state_manager.restore_module_state(SERVICE_NAME)
        return {"success": False, "error": install_result.get("error", "Install failed")}

    restore_forgejo_permissions()
    new_version = get_forgejo_version()
    if new_version != latest_version:
        log_message(f"Version mismatch after update: expected {latest_version}, got {new_version}", "WARNING")
    log_message(f"Forgejo updated {current_version} -> {new_version or latest_version}")
    return {"success": True, "updated": True, "old_version": current_version, "new_version": new_version or latest_version}


if __name__ == "__main__":
    main()
