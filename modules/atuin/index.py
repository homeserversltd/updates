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

import os
import subprocess
import sys
import shutil
import pwd
import urllib.request
import json
from updates.index import log_message
from updates.utils.state_manager import StateManager

# Load module configuration from index.json
def load_module_config():
    """
    Load configuration from the module's index.json file.
    Returns:
        dict: Configuration data or default values if loading fails
    """
    try:
        config_path = os.path.join(os.path.dirname(__file__), "index.json")
        with open(config_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        log_message(f"Failed to load module config: {e}", "WARNING")
        # Return default configuration
        return {
            "metadata": {
                "schema_version": "1.0.0",
                "module_name": "atuin"
            },
            "config": {
                "admin_user_uid": 1000,
                "directories": {
                    "atuin_root": "/home/{admin_user}/.atuin",
                    "atuin_bin": "/home/{admin_user}/.atuin/bin/atuin",
                    "atuin_env": "/home/{admin_user}/.atuin/bin/env",
                    "config_dir": "/home/{admin_user}/.config/atuin",
                    "data_dir": "/home/{admin_user}/.local/share/atuin"
                },
                "backup": {
                    "backup_dir": "/var/backups/updates",
                    "max_age_days": 30,
                    "keep_minimum": 5,
                    "include_paths": [
                        "{atuin_root}",
                        "{config_dir}",
                        "{data_dir}"
                    ]
                },
                "installation": {
                    "install_script_url": "https://setup.atuin.sh",
                    "github_api_url": "https://api.github.com/repos/atuinsh/atuin/releases/latest"
                }
            }
        }

# Global configuration
MODULE_CONFIG = load_module_config()

# --- Helpers for user management ---
def get_admin_user():
    """
    Get the admin username by checking common locations and patterns.
    Returns:
        str: Username or None if not found
    """
    try:
        # Try to find atuin installations in common user directories
        for user_dir in os.listdir("/home"):
            user_path = f"/home/{user_dir}"
            if os.path.isdir(user_path):
                # Check if this user has atuin installed
                atuin_paths = [
                    f"{user_path}/.atuin",
                    f"{user_path}/.atuin/bin/atuin",
                    f"{user_path}/.config/atuin"
                ]
                if any(os.path.exists(path) for path in atuin_paths):
                    log_message(f"Found atuin installation for user: {user_dir}", "DEBUG")
                    return user_dir
        
        # Fallback: try to get the first non-system user (UID >= 1000)
        for user in pwd.getpwall():
            if user.pw_uid >= 1000 and user.pw_uid < 65534:  # Skip nobody user
                log_message(f"Using fallback admin user: {user.pw_name}", "DEBUG")
                return user.pw_name
        
        log_message("Could not determine admin user from system", "ERROR")
        return None
        
    except Exception as e:
        log_message(f"Failed to get admin user: {e}", "ERROR")
        return None

def format_path(path_template, admin_user):
    """
    Format a path template with the admin user name.
    Args:
        path_template: Path template with {admin_user} placeholder
        admin_user: Admin username to substitute
    Returns:
        str: Formatted path
    """
    return path_template.format(admin_user=admin_user)

def get_atuin_bin_path(admin_user):
    """
    Get the path to the Atuin binary for the given user.
    """
    path_template = MODULE_CONFIG["config"]["directories"]["atuin_bin"]
    return format_path(path_template, admin_user)

def get_atuin_config_dir(admin_user):
    """
    Get the path to the Atuin config directory for the given user.
    """
    path_template = MODULE_CONFIG["config"]["directories"]["config_dir"]
    return format_path(path_template, admin_user)

def get_atuin_data_dir(admin_user):
    """
    Get the path to the Atuin data directory for the given user.
    """
    path_template = MODULE_CONFIG["config"]["directories"]["data_dir"]
    return format_path(path_template, admin_user)

def get_atuin_env_file(admin_user):
    """
    Get the path to the Atuin environment file for the given user.
    """
    path_template = MODULE_CONFIG["config"]["directories"]["atuin_env"]
    return format_path(path_template, admin_user)

def get_atuin_root_dir(admin_user):
    """
    Get the path to the Atuin root directory for the given user.
    """
    path_template = MODULE_CONFIG["config"]["directories"]["atuin_root"]
    return format_path(path_template, admin_user)

def get_all_atuin_paths():
    """
    Get all Atuin-related paths that should be backed up.
    Returns:
        list: List of paths that exist and should be backed up
    """
    admin_user = get_admin_user()
    if not admin_user:
        return []
    
    # Common atuin paths for the detected user
    potential_paths = [
        f"/home/{admin_user}/.atuin",
        f"/home/{admin_user}/.config/atuin", 
        f"/home/{admin_user}/.local/share/atuin"
    ]
    
    # Only return paths that actually exist
    existing_paths = []
    for path in potential_paths:
        if os.path.exists(path):
            existing_paths.append(path)
            log_message(f"Found Atuin path for backup: {path}")
        else:
            log_message(f"Atuin path not found (skipping): {path}", "DEBUG")
    
    return existing_paths

def get_installation_config():
    """
    Get installation configuration from module config.
    Returns:
        dict: Installation configuration
    """
    return MODULE_CONFIG["config"]["installation"]

# --- Backup and State Management ---
def create_atuin_backup(description="manual_backup"):
    """
    Create a comprehensive backup of all Atuin files using StateManager.
    
    Args:
        description: Description for the backup
        
    Returns:
        dict: Backup information with rollback point details
    """
    try:
        state_manager = StateManager()  # Use default backup directory
        files_to_backup = get_all_atuin_paths()
        
        if not files_to_backup:
            return {"success": False, "error": "No Atuin files found"}
        
        success = state_manager.backup_module_state(
            module_name=MODULE_CONFIG["metadata"]["module_name"],
            description=description,
            files=files_to_backup
        )
        
        if not success:
            return {"success": False, "error": "Failed to create backup"}
            
        backup_info = state_manager.get_backup_info(MODULE_CONFIG["metadata"]["module_name"])
        
        return {
            "success": True,
            "backup_info": backup_info,
            "files_backed_up": len(files_to_backup),
            "backup_paths": files_to_backup
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}

def restore_atuin_backup():
    """
    Restore Atuin from its backup using StateManager.
    
    Returns:
        dict: Restoration results
    """
    try:
        state_manager = StateManager()  # Use default backup directory
        success = state_manager.restore_module_state(MODULE_CONFIG["metadata"]["module_name"])
        
        # Verify restoration if successful
        verification = None
        if success:
            admin_user = get_admin_user()
            if admin_user:
                verification = verify_atuin_installation(admin_user)
        
        return {
            "success": success,
            "verification": verification
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}

def list_atuin_backups():
    """
    List all available Atuin backups using StateManager.
    
    Returns:
        list: List of BackupInfo objects for Atuin module
    """
    try:
        state_manager = StateManager()  # Use default backup directory
        backup_info = state_manager.get_backup_info(MODULE_CONFIG["metadata"]["module_name"])
        return [backup_info] if backup_info else []
    except Exception as e:
        log_message(f"Failed to list Atuin backups: {e}", "ERROR")
        return []

def cleanup_atuin_backups():
    """
    Clean up old Atuin backups using configuration defaults.
    
    Returns:
        bool: True if cleanup successful
    """
    try:
        state_manager = StateManager()
        return state_manager.remove_module_backup(MODULE_CONFIG["metadata"]["module_name"])
    except Exception as e:
        log_message(f"Failed to cleanup Atuin backups: {e}", "ERROR")
        return False

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
            required_config_sections = ["directories", "installation"]
            for section in required_config_sections:
                if section not in config["config"]:
                    validation_results["errors"].append(f"Missing required config section: {section}")
                    validation_results["valid"] = False
            
            # Check directories section
            if "directories" in config["config"]:
                required_dirs = ["atuin_root", "atuin_bin", "atuin_env", "config_dir", "data_dir"]
                for dir_key in required_dirs:
                    if dir_key not in config["config"]["directories"]:
                        validation_results["warnings"].append(f"Missing directory config: {dir_key}")
        
    except Exception as e:
        validation_results["errors"].append(f"Configuration validation error: {e}")
        validation_results["valid"] = False
    
    return validation_results

# --- Atuin version helpers ---
def get_atuin_version():
    """Detect currently installed Atuin version."""
    admin_user = get_admin_user()
    if not admin_user:
        return None
    
    try:
        bin_path = get_atuin_bin_path(admin_user)
        if not os.path.isfile(bin_path) or not os.access(bin_path, os.X_OK):
            return None
        
        result = subprocess.run([bin_path, "--version"], capture_output=True, text=True, check=False)
        if result.returncode == 0:
            version_parts = result.stdout.strip().split()
            if len(version_parts) >= 2:
                return version_parts[1]
        return None
    except Exception as e:
        log_message(f"Warning: Failed to detect Atuin version: {e}")
        return None

def check_atuin_version(bin_path):
    """
    Check the current version of Atuin if installed at bin_path.
    Returns:
        str: Version string or None if not installed
    """
    try:
        if not os.path.isfile(bin_path) or not os.access(bin_path, os.X_OK):
            return None
        result = subprocess.run([bin_path, "--version"], capture_output=True, text=True, check=False)
        if result.returncode == 0:
            version_parts = result.stdout.strip().split()
            if len(version_parts) >= 2:
                return version_parts[1]
        return None
    except Exception:
        return None

def get_latest_atuin_version():
    """
    Get the latest Atuin version from GitHub releases using configured URL.
    Returns:
        str: Latest version string or None
    """
    try:
        api_url = get_installation_config()["github_api_url"]
        with urllib.request.urlopen(api_url) as resp:
            data = json.load(resp)
            tag = data.get("tag_name", "")
            if tag.startswith("v"):
                return tag[1:]
            return tag
    except Exception as e:
        log_message(f"Failed to get latest version info: {e}", "ERROR")
        return None

def install_atuin(admin_user):
    """
    Install Atuin using the configured installation script.
    Returns:
        bool: True if install succeeded, False otherwise
    """
    log_message("Installing Atuin...", "INFO")
    try:
        # Remove existing binary to prevent permission conflicts during update
        bin_path = get_atuin_bin_path(admin_user)
        if os.path.exists(bin_path):
            log_message(f"Removing existing binary: {bin_path}", "DEBUG")
            try:
                os.remove(bin_path)
            except OSError as e:
                log_message(f"Warning: Could not remove existing binary: {e}", "WARNING")
                # Try with elevated permissions if needed
                try:
                    subprocess.run(f"rm -f {bin_path}", shell=True, check=True)
                except subprocess.CalledProcessError:
                    log_message("Failed to remove existing binary, continuing anyway", "WARNING")
        
        install_url = get_installation_config()["install_script_url"]
        # Use proper shell command construction for process substitution
        shell_command = f"su - {admin_user} -c 'bash <(curl --proto \"=https\" --tlsv1.2 -sSf {install_url})'"
        
        result = subprocess.run(
            shell_command, shell=True, capture_output=True, text=True, check=False
        )
        if result.returncode == 0:
            log_message("Atuin installation successful", "INFO")
            return True
        else:
            log_message(f"Atuin installation failed: {result.stderr}", "ERROR")
            return False
    except Exception as e:
        log_message(f"Error during Atuin installation: {str(e)}", "ERROR")
        return False

def verify_atuin_installation(admin_user):
    """
    Verify that Atuin is properly installed and functional.
    Returns:
        dict: Verification results with status and details
    """
    verification_results = {
        "binary_exists": False,
        "binary_executable": False,
        "version_readable": False,
        "config_dir_exists": False,
        "data_dir_exists": False,
        "env_file_exists": False,
        "root_dir_exists": False,
        "version": None,
        "paths": {}
    }
    
    try:
        # Check binary
        bin_path = get_atuin_bin_path(admin_user)
        verification_results["paths"]["binary"] = bin_path
        
        if os.path.exists(bin_path):
            verification_results["binary_exists"] = True
            if os.access(bin_path, os.X_OK):
                verification_results["binary_executable"] = True
                
                # Check version
                version = check_atuin_version(bin_path)
                if version:
                    verification_results["version_readable"] = True
                    verification_results["version"] = version
        
        # Check directories and files
        config_dir = get_atuin_config_dir(admin_user)
        data_dir = get_atuin_data_dir(admin_user)
        env_file = get_atuin_env_file(admin_user)
        root_dir = get_atuin_root_dir(admin_user)
        
        verification_results["paths"]["config_dir"] = config_dir
        verification_results["paths"]["data_dir"] = data_dir
        verification_results["paths"]["env_file"] = env_file
        verification_results["paths"]["root_dir"] = root_dir
        
        verification_results["config_dir_exists"] = os.path.exists(config_dir)
        verification_results["data_dir_exists"] = os.path.exists(data_dir)
        verification_results["env_file_exists"] = os.path.exists(env_file)
        verification_results["root_dir_exists"] = os.path.exists(root_dir)
        
        # Log verification results
        for check, result in verification_results.items():
            if check not in ["version", "paths"]:
                status = "✓" if result else "✗"
                log_message(f"Atuin verification - {check}: {status}")
        
        if verification_results["version"]:
            log_message(f"Atuin verification - version: {verification_results['version']}")
        
    except Exception as e:
        log_message(f"Error during Atuin verification: {e}", "ERROR")
    
    return verification_results

def main(args=None):
    """
    Main entry point for Atuin update module.
    Args:
        args: List of arguments (supports '--check', '--verify', '--config')
    Returns:
        dict: Status and results of the update
    """
    if args is None:
        args = []
    
    log_message("Starting Atuin module update...")
    
    SERVICE_NAME = MODULE_CONFIG["metadata"]["module_name"]
    admin_user = get_admin_user()
    if not admin_user:
        log_message("Could not determine admin user from configuration", "ERROR")
        return {"success": False, "error": "No admin user"}
    
    ATUIN_BIN = get_atuin_bin_path(admin_user)

    # --config mode: show current configuration
    if len(args) > 0 and args[0] == "--config":
        log_message("Current Atuin module configuration:")
        log_message(f"  Admin user: {admin_user}")
        log_message(f"  Binary path: {ATUIN_BIN}")
        log_message(f"  Config dir: {get_atuin_config_dir(admin_user)}")
        log_message(f"  Data dir: {get_atuin_data_dir(admin_user)}")
        log_message(f"  Root dir: {get_atuin_root_dir(admin_user)}")
        
        state_manager = StateManager()
        log_message(f"  Backup dir: {state_manager.backup_root}")
        
        return {
            "success": True,
            "config": MODULE_CONFIG,
            "admin_user": admin_user,
            "paths": {
                "binary": ATUIN_BIN,
                "config_dir": get_atuin_config_dir(admin_user),
                "data_dir": get_atuin_data_dir(admin_user),
                "root_dir": get_atuin_root_dir(admin_user)
            }
        }

    # --verify mode: comprehensive installation verification
    if len(args) > 0 and args[0] == "--verify":
        log_message("Running comprehensive Atuin verification...")
        verification = verify_atuin_installation(admin_user)
        
        all_checks_passed = all([
            verification["binary_exists"],
            verification["binary_executable"], 
            verification["version_readable"]
        ])
        
        return {
            "success": all_checks_passed,
            "verification": verification,
            "version": verification.get("version"),
            "config": MODULE_CONFIG
        }

    # --check mode: simple version check
    if len(args) > 0 and args[0] == "--check":
        version = check_atuin_version(ATUIN_BIN)
        if version:
            log_message(f"OK - Current version: {version}")
            return {"success": True, "version": version}
        else:
            log_message(f"Atuin binary not found at {ATUIN_BIN}", "ERROR")
            return {"success": False, "error": "Not found"}

    # Get current version
    current_version = check_atuin_version(ATUIN_BIN)
    if not current_version:
        log_message("Failed to get current version of Atuin", "ERROR")
        return {"success": False, "error": "No current version"}
    log_message(f"Current Atuin version: {current_version}")

    # Get latest version
    latest_version = get_latest_atuin_version()
    if not latest_version:
        log_message("Failed to get latest version information", "ERROR")
        return {"success": False, "error": "No latest version"}
    log_message(f"Latest available version: {latest_version}")

    # Compare and update if needed
    if current_version != latest_version:
        log_message("Update available. Creating comprehensive backup...")
        
        # Initialize StateManager with default backup directory
        state_manager = StateManager()
        
        # Get all Atuin-related paths for comprehensive backup
        files_to_backup = get_all_atuin_paths()
        
        if not files_to_backup:
            log_message("No Atuin files found for backup", "WARNING")
            return {"success": False, "error": "No files to backup"}
        
        log_message(f"Creating backup for {len(files_to_backup)} Atuin paths...")
        
        # Create backup using the simplified API
        backup_success = state_manager.backup_module_state(
            module_name=SERVICE_NAME,
            description=f"pre_update_{current_version}_to_{latest_version}",
            files=files_to_backup
        )
        
        if not backup_success:
            log_message("Failed to create backup", "ERROR")
            return {"success": False, "error": "Backup failed"}
        
        log_message("Backup created successfully")
        
        # Perform the update
        log_message("Installing update...")
        try:
            if not install_atuin(admin_user):
                raise Exception("Atuin installation failed")
            
            # Verify new installation
            log_message("Verifying new installation...")
            verification = verify_atuin_installation(admin_user)
            new_version = verification.get("version")
            
            if new_version == latest_version:
                log_message(f"Successfully updated Atuin from {current_version} to {latest_version}")
                
                # Run post-update verification
                if not verification["binary_executable"] or not verification["version_readable"]:
                    raise Exception("Post-update verification failed - installation appears incomplete")
                
                return {
                    "success": True, 
                    "updated": True, 
                    "old_version": current_version, 
                    "new_version": new_version,
                    "verification": verification,
                    "config": MODULE_CONFIG
                }
            else:
                raise Exception(f"Version mismatch after update. Expected: {latest_version}, Got: {new_version}")
                
        except Exception as e:
            log_message(f"Update failed: {e}", "ERROR")
            log_message("Restoring from backup...")
            
            # Restore using simplified API
            rollback_success = state_manager.restore_module_state(SERVICE_NAME)
            
            if rollback_success:
                log_message("Successfully restored from backup")
                # Verify rollback worked
                restored_version = check_atuin_version(ATUIN_BIN)
                log_message(f"Restored version: {restored_version}")
            else:
                log_message("Failed to restore from backup", "ERROR")
            
            return {
                "success": False, 
                "error": str(e),
                "rollback_success": rollback_success,
                "restored_version": check_atuin_version(ATUIN_BIN) if rollback_success else None,
                "config": MODULE_CONFIG
            }
    else:
        log_message(f"Atuin is already at the latest version ({current_version})")
        
        # Still run verification to ensure everything is working
        verification = verify_atuin_installation(admin_user)
        
        return {
            "success": True, 
            "updated": False, 
            "version": current_version,
            "verification": verification,
            "config": MODULE_CONFIG
        }

if __name__ == "__main__":
    main()
