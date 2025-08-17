#!/usr/bin/env python3
"""
HOMESERVER Update Management System
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
along with this program.  If not, see <https://www.gnu/licenses/>.
"""

"""
Module Self-Update Utility

This module provides functionality for modules to update themselves before execution.
This is critical for self-modifying code that needs to ensure it's running the latest
schema version before processing updates.

Usage:
    from updates.utils.module_self_update import ensure_module_self_updated
    
    def main(args=None):
        # Ensure module is up-to-date before running
        if not ensure_module_self_updated():
            return {"success": False, "error": "Module self-update failed"}
        
        # Now run with latest code
        return run_module_logic()
"""

import os
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from .index import log_message
from .state_manager import StateManager


class ModuleSelfUpdateError(Exception):
    """Exception raised when module self-update fails."""
    pass


def load_module_config(module_dir: Path) -> Dict[str, Any]:
    """Load module configuration from index.json."""
    config_file = module_dir / "index.json"
    
    if not config_file.exists():
        raise ModuleSelfUpdateError(f"Module config not found: {config_file}")
    
    try:
        with open(config_file, 'r') as f:
            return json.load(f)
    except Exception as e:
        raise ModuleSelfUpdateError(f"Failed to load module config: {e}")


def get_repository_info(module_dir: Path) -> Tuple[str, str]:
    """Get repository URL and branch from module config."""
    config = load_module_config(module_dir)
    
    repo_config = config.get("repo", {})
    repo_url = repo_config.get("url")
    repo_branch = repo_config.get("branch", "master")
    
    if not repo_url:
        raise ModuleSelfUpdateError("Module has no repository URL configured")
    
    return repo_url, repo_branch


def get_local_schema_version(module_dir: Path) -> str:
    """Get the current schema version from local module."""
    config = load_module_config(module_dir)
    return config.get("metadata", {}).get("schema_version", "0.0.0")


def get_repository_schema_version(repo_url: str, repo_branch: str, module_name: str) -> str:
    """Get the schema version from repository."""
    try:
        # Create temporary directory for repository checkout
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Clone repository
            log_message(f"Cloning repository to check schema version: {repo_url}")
            subprocess.run([
                "git", "clone", "--depth", "1", "--branch", repo_branch, 
                repo_url, str(temp_path)
            ], check=True, capture_output=True)
            
            # Look for module in repository
            module_path = temp_path / "modules" / module_name
            if not module_path.exists():
                raise ModuleSelfUpdateError(f"Module {module_name} not found in repository")
            
            # Load repository module config
            repo_config = load_module_config(module_path)
            return repo_config.get("metadata", {}).get("schema_version", "0.0.0")
            
    except subprocess.CalledProcessError as e:
        raise ModuleSelfUpdateError(f"Failed to clone repository: {e}")
    except Exception as e:
        raise ModuleSelfUpdateError(f"Failed to get repository schema version: {e}")


def compare_versions(local_version: str, repo_version: str) -> int:
    """
    Compare two semantic versions.
    
    Returns:
        -1 if local < repo (update needed)
         0 if local == repo (no update needed)
        +1 if local > repo (local is newer)
    """
    def version_to_tuple(version: str) -> Tuple[int, ...]:
        try:
            return tuple(int(x) for x in version.split('.'))
        except (ValueError, AttributeError):
            return (0, 0, 0)
    
    local_tuple = version_to_tuple(local_version)
    repo_tuple = version_to_tuple(repo_version)
    
    if local_tuple < repo_tuple:
        return -1
    elif local_tuple > repo_tuple:
        return 1
    else:
        return 0


def module_needs_schema_update(module_dir: Path) -> bool:
    """
    Check if module needs to update itself due to schema version mismatch.
    
    Args:
        module_dir: Path to the module directory
        
    Returns:
        True if module needs self-update, False otherwise
    """
    try:
        # Get local schema version
        local_version = get_local_schema_version(module_dir)
        log_message(f"Local module schema version: {local_version}")
        
        # Get repository info
        repo_url, repo_branch = get_repository_info(module_dir)
        
        # Get repository schema version
        repo_version = get_repository_schema_version(repo_url, repo_branch, module_dir.name)
        log_message(f"Repository module schema version: {repo_version}")
        
        # Compare versions
        comparison = compare_versions(local_version, repo_version)
        
        if comparison < 0:
            log_message(f"🚨 Module needs self-update: {local_version} → {repo_version}")
            return True
        elif comparison > 0:
            log_message(f"⚠️ Local module is newer than repository: {local_version} > {repo_version}")
            return False
        else:
            log_message(f"✓ Module schema versions match: {local_version}")
            return False
            
    except ModuleSelfUpdateError as e:
        log_message(f"⚠️ Could not determine if update needed: {e}", "WARNING")
        return False
    except Exception as e:
        log_message(f"✗ Error checking module update status: {e}", "ERROR")
        return False


def update_module_self(module_dir: Path) -> bool:
    """
    Update the module with the latest version from repository.
    
    Args:
        module_dir: Path to the module directory
        
    Returns:
        True if update successful, False otherwise
    """
    try:
        module_name = module_dir.name
        log_message(f"Starting self-update for module: {module_name}")
        
        # Get repository info
        repo_url, repo_branch = get_repository_info(module_dir)
        
        # Create backup of current module
        state_manager = StateManager("/var/backups/updates")
        backup_success = state_manager.backup_module_state(
            module_name=f"{module_name}_self_update",
            description=f"Pre-self-update backup of {module_name}",
            files=[str(module_dir)]
        )
        
        if not backup_success:
            log_message(f"⚠️ Failed to create backup for {module_name}, continuing anyway", "WARNING")
        
        # Create temporary directory for repository checkout
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Clone repository
            log_message(f"Cloning repository for module update: {repo_url}")
            subprocess.run([
                "git", "clone", "--depth", "1", "--branch", repo_branch, 
                repo_url, str(temp_path)
            ], check=True, capture_output=True)
            
            # Find module in repository
            repo_module_path = temp_path / "modules" / module_name
            if not repo_module_path.exists():
                raise ModuleSelfUpdateError(f"Module {module_name} not found in repository")
            
            # Remove current module directory
            if module_dir.exists():
                shutil.rmtree(module_dir)
            
            # Copy new module from repository
            shutil.copytree(repo_module_path, module_dir)
            
            log_message(f"✓ Successfully updated module {module_name}")
            return True
            
    except subprocess.CalledProcessError as e:
        log_message(f"✗ Git operation failed during module update: {e}", "ERROR")
        return False
    except Exception as e:
        log_message(f"✗ Module self-update failed: {e}", "ERROR")
        return False


def restart_with_new_code(module_dir: Path) -> Dict[str, Any]:
    """
    Restart the module with new code after self-update.
    
    This is a placeholder - the actual restart mechanism depends on how
    the module is being executed (orchestrator, direct call, etc.)
    
    Args:
        module_dir: Path to the module directory
        
    Returns:
        Dict indicating restart status
    """
    module_name = module_dir.name
    
    log_message(f"✓ Module {module_name} updated successfully")
    log_message(f"🔄 Module needs to be restarted to use new code")
    log_message(f"💡 This module should be re-executed by the orchestrator")
    
    # Return success but indicate restart is needed
    return {
        "success": True,
        "updated": True,
        "restart_needed": True,
        "message": f"Module {module_name} updated successfully, restart required"
    }


def ensure_module_self_updated(module_dir: Optional[Path] = None) -> bool:
    """
    Ensure module is running the latest schema version.
    
    This is the main function modules should call at the start of main().
    
    Args:
        module_dir: Path to module directory (defaults to __file__.parent)
        
    Returns:
        True if module is up-to-date, False if self-update failed
    """
    if module_dir is None:
        # Default to the directory containing the calling module
        import inspect
        caller_frame = inspect.currentframe().f_back
        caller_file = caller_frame.f_globals.get('__file__')
        if caller_file:
            module_dir = Path(caller_file).parent
        else:
            log_message("⚠️ Could not determine module directory", "WARNING")
            return True  # Continue anyway
    
    try:
        # Check if module needs self-update
        if not module_needs_schema_update(module_dir):
            return True  # No update needed
        
        # Perform self-update
        if not update_module_self(module_dir):
            return False
        
        # Indicate restart is needed
        log_message("🔄 Module self-update completed - restart required")
        return False  # Return False to indicate restart needed
        
    except Exception as e:
        log_message(f"✗ Module self-update check failed: {e}", "ERROR")
        return False


# Convenience function for easy import
def check_and_update_module() -> bool:
    """
    Convenience function that automatically determines module directory.
    
    Usage:
        from updates.utils.module_self_update import check_and_update_module
        
        def main(args=None):
            if not check_and_update_module():
                return {"success": False, "error": "Module self-update failed"}
            
            # Continue with module logic
            return run_module_logic()
    """
    return ensure_module_self_updated()
