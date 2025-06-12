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
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

"""
Atuin Update Module

Handles update logic specific to the Atuin service.
Implements a main(args) entrypoint for orchestrated updates.
Provides comprehensive backup and rollback capabilities.
Uses configuration from index.json for all paths and settings.
"""
# Import common functionality from parent package
from initialization.files.user_local_lib.updates import log_message, run_update
from .index import (
    main, 
    verify_atuin_installation, 
    get_all_atuin_paths, 
    get_admin_user,
    load_module_config,
    get_backup_config,
    get_installation_config,
    MODULE_CONFIG
)

# Import state management utilities
from ...utils.state_manager import StateManager

# Module integrity - no longer using checksums, relying on schema versioning

# Convenience functions for external use
def create_atuin_backup(description="manual_backup"):
    """
    Create a comprehensive backup of all Atuin files using configuration.
    
    Args:
        description: Description for the backup
        
    Returns:
        dict: Backup information with rollback point details
    """
    admin_user = get_admin_user()
    if not admin_user:
        return {"success": False, "error": "No admin user found"}
    
    try:
        backup_config = get_backup_config()
        rollback = GlobalRollback(backup_config["backup_dir"])
        files_to_backup = get_all_atuin_paths(admin_user)
        
        if not files_to_backup:
            return {"success": False, "error": "No Atuin files found"}
        
        rollback_point = rollback.create_rollback_point(
            module_name=MODULE_CONFIG["metadata"]["module_name"],
            description=description,
            files=files_to_backup
        )
        
        return {
            "success": True,
            "rollback_point": rollback_point,
            "files_backed_up": len(files_to_backup),
            "backup_paths": files_to_backup,
            "backup_config": backup_config
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}

def restore_atuin_backup(rollback_point):
    """
    Restore Atuin from a rollback point using configuration.
    
    Args:
        rollback_point: Dict containing backup IDs from create_atuin_backup
        
    Returns:
        dict: Restoration results
    """
    try:
        backup_config = get_backup_config()
        rollback = GlobalRollback(backup_config["backup_dir"])
        success = rollback.restore_rollback_point(rollback_point)
        
        # Verify restoration if successful
        verification = None
        if success:
            admin_user = get_admin_user()
            if admin_user:
                verification = verify_atuin_installation(admin_user)
        
        return {
            "success": success,
            "verification": verification,
            "backup_config": backup_config
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}

def list_atuin_backups():
    """
    List all available Atuin backups using configuration.
    
    Returns:
        list: List of BackupInfo objects for Atuin module
    """
    try:
        backup_config = get_backup_config()
        rollback = GlobalRollback(backup_config["backup_dir"])
        return rollback.list_backups(module_name=MODULE_CONFIG["metadata"]["module_name"])
    except Exception as e:
        log_message(f"Failed to list Atuin backups: {e}", "ERROR")
        return []

def cleanup_atuin_backups(max_age_days=None, keep_minimum=None):
    """
    Clean up old Atuin backups using configuration defaults or provided values.
    
    Args:
        max_age_days: Maximum age in days for backups (uses config default if None)
        keep_minimum: Minimum number of backups to keep (uses config default if None)
        
    Returns:
        int: Number of backups removed
    """
    try:
        backup_config = get_backup_config()
        rollback = GlobalRollback(backup_config["backup_dir"])
        
        # Use config defaults if not provided
        max_age = max_age_days if max_age_days is not None else backup_config["max_age_days"]
        keep_min = keep_minimum if keep_minimum is not None else backup_config["keep_minimum"]
        
        return rollback.cleanup_old_backups(max_age, keep_min)
    except Exception as e:
        log_message(f"Failed to cleanup Atuin backups: {e}", "ERROR")
        return 0

def get_atuin_config():
    """
    Get the current Atuin module configuration.
    
    Returns:
        dict: Complete module configuration
    """
    return MODULE_CONFIG

def reload_atuin_config():
    """
    Reload the Atuin module configuration from index.json.
    
    Returns:
        dict: Reloaded configuration
    """
    global MODULE_CONFIG
    MODULE_CONFIG = load_module_config()
    return MODULE_CONFIG

def validate_atuin_config():
    """
    Validate the current Atuin configuration.
    
    Returns:
        dict: Validation results
    """
    config = MODULE_CONFIG
    validation_results = {
        "valid": True,
        "errors": [],
        "warnings": []
    }
    
    try:
        # Check required sections
        required_sections = ["metadata", "config"]
        for section in required_sections:
            if section not in config:
                validation_results["errors"].append(f"Missing required section: {section}")
                validation_results["valid"] = False
        
        if "config" in config:
            # Check required config subsections
            required_config_sections = ["admin_user_uid", "directories", "backup", "installation"]
            for section in required_config_sections:
                if section not in config["config"]:
                    validation_results["errors"].append(f"Missing required config section: {section}")
                    validation_results["valid"] = False
            
            # Check admin user UID
            if "admin_user_uid" in config["config"]:
                try:
                    uid = config["config"]["admin_user_uid"]
                    if not isinstance(uid, int) or uid < 0:
                        validation_results["errors"].append("admin_user_uid must be a positive integer")
                        validation_results["valid"] = False
                except Exception:
                    validation_results["errors"].append("Invalid admin_user_uid format")
                    validation_results["valid"] = False
            
            # Check directories section
            if "directories" in config["config"]:
                required_dirs = ["atuin_root", "atuin_bin", "atuin_env", "config_dir", "data_dir"]
                for dir_key in required_dirs:
                    if dir_key not in config["config"]["directories"]:
                        validation_results["warnings"].append(f"Missing directory config: {dir_key}")
            
            # Check backup section
            if "backup" in config["config"]:
                backup_config = config["config"]["backup"]
                if "include_paths" not in backup_config:
                    validation_results["warnings"].append("No backup include_paths specified")
                
                # Check numeric values
                for key in ["max_age_days", "keep_minimum"]:
                    if key in backup_config:
                        try:
                            val = backup_config[key]
                            if not isinstance(val, int) or val < 0:
                                validation_results["warnings"].append(f"backup.{key} should be a positive integer")
                        except Exception:
                            validation_results["warnings"].append(f"Invalid backup.{key} format")
        
    except Exception as e:
        validation_results["errors"].append(f"Configuration validation error: {e}")
        validation_results["valid"] = False
    
    return validation_results

# Make functions available at the module level
__all__ = [
    'main', 
    'log_message', 
    'verify_atuin_installation',
    'get_all_atuin_paths',
    'create_atuin_backup',
    'restore_atuin_backup', 
    'list_atuin_backups',
    'cleanup_atuin_backups',
    'get_atuin_config',
    'reload_atuin_config',
    'validate_atuin_config',
    'get_backup_config',
    'get_installation_config',
    'MODULE_CONFIG'
]

# This allows the module to be run directly
if __name__ == "__main__":
    import sys
    main(sys.argv[1:] if len(sys.argv) > 1 else []) 