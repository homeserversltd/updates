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
from pathlib import Path
import subprocess
import sys
import shutil
import pwd
import urllib.request
import json
from updates.index import log_message
from updates.utils.state_manager import StateManager
from updates.utils.permissions import PermissionManager, PermissionTarget

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
        return {
            "metadata": {
                "schema_version": "1.0.0",
                "module_name": "zoxide"
            },
            "config": {
                "directories": {
                    "zoxide_bin": "/home/{admin_user}/.local/bin/zoxide",
                    "config_dir": "/home/{admin_user}/.config/zoxide",
                    "data_dir": "/home/{admin_user}/.local/share/zoxide"
                },
                "installation": {
                    "install_script_url": "https://raw.githubusercontent.com/ajeetdsouza/zoxide/main/install.sh",
                    "github_api_url": "https://api.github.com/repos/ajeetdsouza/zoxide/releases/latest"
                }
            }
        }

# Global configuration
MODULE_CONFIG = load_module_config()

def get_admin_user():
    """
    Get the admin username by checking common locations and patterns.
    Returns:
        str: Username or None if not found
    """
    try:
        # Try to find zoxide installations in common user directories
        for user_dir in os.listdir("/home"):
            user_path = f"/home/{user_dir}"
            if os.path.isdir(user_path):
                zoxide_paths = [
                    f"{user_path}/.local/bin/zoxide",
                    f"{user_path}/.config/zoxide",
                    f"{user_path}/.local/share/zoxide"
                ]
                if any(os.path.exists(path) for path in zoxide_paths):
                    log_message(f"Found zoxide installation for user: {user_dir}", "DEBUG")
                    return user_dir
        
        # Fallback: try to get the first non-system user (UID >= 1000)
        for user in pwd.getpwall():
            if user.pw_uid >= 1000 and user.pw_uid < 65534:
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

def get_directory_path(config, key, admin_user, default_path=None):
    """Helper function to get directory path from either new or legacy format."""
    dir_config = config.get(key, default_path)
    if isinstance(dir_config, dict):
        path_template = dir_config["path"]
    else:
        path_template = dir_config
    
    if path_template and "{admin_user}" in path_template:
        return format_path(path_template, admin_user)
    return path_template

def get_zoxide_bin_path(admin_user):
    """Get the path to the zoxide binary for the given user."""
    directories = MODULE_CONFIG["config"]["directories"]
    return get_directory_path(directories, "zoxide_bin", admin_user, "/home/{admin_user}/.local/bin/zoxide")

def get_zoxide_config_dir(admin_user):
    """Get the path to the zoxide config directory for the given user."""
    directories = MODULE_CONFIG["config"]["directories"]
    return get_directory_path(directories, "config_dir", admin_user, "/home/{admin_user}/.config/zoxide")

def get_zoxide_data_dir(admin_user):
    """Get the path to the zoxide data directory for the given user."""
    directories = MODULE_CONFIG["config"]["directories"]
    return get_directory_path(directories, "data_dir", admin_user, "/home/{admin_user}/.local/share/zoxide")

def get_all_zoxide_paths():
    """Get all zoxide-related paths that should be backed up."""
    admin_user = get_admin_user()
    if not admin_user:
        return []
    
    potential_paths = [
        f"/home/{admin_user}/.local/bin/zoxide",
        f"/home/{admin_user}/.config/zoxide",
        f"/home/{admin_user}/.local/share/zoxide"
    ]
    
    existing_paths = []
    for path in potential_paths:
        if os.path.exists(path):
            existing_paths.append(path)
            log_message(f"Found zoxide path for backup: {path}")
    
    return existing_paths

def get_installation_config():
    """Get installation configuration from module config."""
    return MODULE_CONFIG["config"]["installation"]

def check_zoxide_version(bin_path):
    """Check the version of zoxide binary."""
    try:
        if not os.path.exists(bin_path):
            return None
        result = subprocess.run([bin_path, "--version"], capture_output=True, text=True, check=True)
        version_line = result.stdout.strip()
        # zoxide outputs: "zoxide 0.9.4" or similar
        if version_line.startswith("zoxide "):
            return version_line.split()[1]
        return version_line
    except Exception:
        return None

def get_latest_zoxide_version():
    """Get the latest zoxide version from GitHub releases."""
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

def install_zoxide(admin_user):
    """Install zoxide using the configured installation script."""
    log_message("Installing zoxide...", "INFO")
    try:
        bin_path = get_zoxide_bin_path(admin_user)
        if os.path.exists(bin_path):
            log_message(f"Removing existing binary: {bin_path}", "DEBUG")
            try:
                os.remove(bin_path)
            except OSError:
                try:
                    subprocess.run(f"rm -f {bin_path}", shell=True, check=True)
                except subprocess.CalledProcessError:
                    log_message("Failed to remove existing binary, continuing anyway", "WARNING")
        
        install_url = get_installation_config()["install_script_url"]
        shell_command = f"su - {admin_user} -c 'curl -sS {install_url} | bash'"
        
        result = subprocess.run(
            shell_command, shell=True, capture_output=True, text=True, check=False
        )
        if result.returncode == 0:
            log_message("Zoxide installation successful", "INFO")
            return True
        else:
            log_message(f"Zoxide installation failed: {result.stderr}", "ERROR")
            return False
    except Exception as e:
        log_message(f"Error during zoxide installation: {str(e)}", "ERROR")
        return False

def verify_zoxide_installation(admin_user):
    """Verify that zoxide is properly installed and functional."""
    verification_results = {
        "binary_exists": False,
        "binary_executable": False,
        "version_readable": False,
        "config_dir_exists": False,
        "data_dir_exists": False,
        "version": None,
        "paths": {}
    }
    
    try:
        bin_path = get_zoxide_bin_path(admin_user)
        verification_results["paths"]["binary"] = bin_path
        
        if os.path.exists(bin_path):
            verification_results["binary_exists"] = True
            if os.access(bin_path, os.X_OK):
                verification_results["binary_executable"] = True
                version = check_zoxide_version(bin_path)
                if version:
                    verification_results["version_readable"] = True
                    verification_results["version"] = version
        
        config_dir = get_zoxide_config_dir(admin_user)
        data_dir = get_zoxide_data_dir(admin_user)
        
        verification_results["paths"]["config_dir"] = config_dir
        verification_results["paths"]["data_dir"] = data_dir
        
        verification_results["config_dir_exists"] = os.path.exists(config_dir)
        verification_results["data_dir_exists"] = os.path.exists(data_dir)
        
        for check, result in verification_results.items():
            if check not in ["version", "paths"]:
                status = "✓" if result else "✗"
                log_message(f"Zoxide verification - {check}: {status}")
        
        if verification_results["version"]:
            log_message(f"Zoxide verification - version: {verification_results['version']}")
        
    except Exception as e:
        log_message(f"Error during zoxide verification: {e}", "ERROR")
    
    return verification_results

def restore_zoxide_permissions(admin_user):
    """Restore proper ownership and permissions for zoxide files and directories."""
    try:
        log_message("Restoring zoxide permissions after update...")
        
        config = MODULE_CONFIG["config"]
        permission_manager = PermissionManager("zoxide")
        
        targets = []
        default_owner = config["permissions"]["owner"]
        default_group = config["permissions"]["group"]
        
        directories = config["directories"]
        for key, dir_config in directories.items():
            if isinstance(dir_config, dict) and dir_config.get("user_relative"):
                path = get_directory_path(directories, key, admin_user)
                if os.path.exists(path):
                    owner = dir_config.get("owner", default_owner)
                    group = dir_config.get("group", default_group)
                    mode = dir_config.get("mode", "755")
                    
                    targets.append(PermissionTarget(
                        path=path,
                        owner=owner,
                        group=group,
                        mode=int(mode, 8) if isinstance(mode, str) else mode,
                        recursive=True
                    ))
        
        success = permission_manager.apply_permissions(targets)
        return success
    except Exception as e:
        log_message(f"Error restoring zoxide permissions: {e}", "ERROR")
        return False

def main(args=None):
    """Main entry point for zoxide update module."""
    if args is None:
        args = []
    
    log_message("Starting zoxide module update...")
    
    SERVICE_NAME = MODULE_CONFIG["metadata"]["module_name"]
    admin_user = get_admin_user()
    if not admin_user:
        log_message("Could not determine admin user from configuration", "ERROR")
        return {"success": False, "error": "No admin user"}
    
    ZOXIDE_BIN = get_zoxide_bin_path(admin_user)

    if len(args) > 0 and args[0] == "--fix-permissions":
        log_message("Restoring zoxide permissions...")
        success = restore_zoxide_permissions(admin_user)
        return {
            "success": success,
            "permissions_restored": success,
            "admin_user": admin_user
        }

    if len(args) > 0 and args[0] == "--config":
        log_message("Current zoxide module configuration:")
        log_message(f"  Admin user: {admin_user}")
        log_message(f"  Binary path: {ZOXIDE_BIN}")
        log_message(f"  Config dir: {get_zoxide_config_dir(admin_user)}")
        log_message(f"  Data dir: {get_zoxide_data_dir(admin_user)}")
        
        state_manager = StateManager()
        log_message(f"  Backup dir: {state_manager.backup_root}")
        
        return {
            "success": True,
            "config": MODULE_CONFIG,
            "admin_user": admin_user,
            "paths": {
                "binary": ZOXIDE_BIN,
                "config_dir": get_zoxide_config_dir(admin_user),
                "data_dir": get_zoxide_data_dir(admin_user)
            }
        }

    if len(args) > 0 and args[0] == "--verify":
        log_message("Running comprehensive zoxide verification...")
        verification = verify_zoxide_installation(admin_user)
        
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

    if len(args) > 0 and args[0] == "--check":
        version = check_zoxide_version(ZOXIDE_BIN)
        if version:
            log_message(f"OK - Current version: {version}")
            return {"success": True, "version": version}
        else:
            log_message(f"Zoxide binary not found at {ZOXIDE_BIN}", "ERROR")
            return {"success": False, "error": "Not found"}

    # Get current version
    current_version = check_zoxide_version(ZOXIDE_BIN)
    if not current_version:
        log_message("Zoxide not installed, performing fresh installation...", "INFO")
        success = install_zoxide(admin_user)
        if success:
            restore_zoxide_permissions(admin_user)
            verification = verify_zoxide_installation(admin_user)
            return {
                "success": True,
                "installed": True,
                "version": verification.get("version"),
                "verification": verification
            }
        return {"success": False, "error": "Installation failed"}

    log_message(f"Current zoxide version: {current_version}")

    # Get latest version
    latest_version = get_latest_zoxide_version()
    if not latest_version:
        log_message("Failed to get latest version information", "ERROR")
        return {"success": False, "error": "No latest version"}

    log_message(f"Latest available version: {latest_version}")

    if current_version == latest_version:
        log_message("Zoxide is already at the latest version", "INFO")
        return {
            "success": True,
            "up_to_date": True,
            "current_version": current_version,
            "latest_version": latest_version
        }

    # Create backup before update
    log_message("Creating backup before update...")
    state_manager = StateManager()
    files_to_backup = get_all_zoxide_paths()
    if files_to_backup:
        state_manager.backup_module_state(
            module_name=SERVICE_NAME,
            description=f"Pre-update backup (v{current_version} -> v{latest_version})",
            files=files_to_backup
        )

    # Perform update
    log_message(f"Updating zoxide from {current_version} to {latest_version}...")
    success = install_zoxide(admin_user)
    
    if not success:
        log_message("Update failed, attempting to restore from backup...", "ERROR")
        state_manager.restore_module_state(SERVICE_NAME)
        return {"success": False, "error": "Update failed"}

    # Restore permissions after update
    restore_zoxide_permissions(admin_user)

    # Verify installation
    verification = verify_zoxide_installation(admin_user)
    new_version = verification.get("version")
    
    if new_version == latest_version:
        log_message(f"Zoxide successfully updated to {latest_version}", "INFO")
        return {
            "success": True,
            "updated": True,
            "previous_version": current_version,
            "current_version": new_version,
            "verification": verification
        }
    else:
        log_message(f"Update completed but version mismatch. Expected {latest_version}, got {new_version}", "WARNING")
        return {
            "success": True,
            "updated": True,
            "previous_version": current_version,
            "current_version": new_version,
            "expected_version": latest_version,
            "verification": verification
        }

if __name__ == "__main__":
    result = main(sys.argv[1:])
    sys.exit(0 if result.get("success") else 1)

