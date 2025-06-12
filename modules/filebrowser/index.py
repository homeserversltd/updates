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
                "module_name": "filebrowser"
            },
            "config": {
                "directories": {
                    "data_dir": "/var/lib/filebrowser",
                    "config_dir": "/etc/filebrowser"
                },
                "installation": {
                    "github_api_url": "https://api.github.com/repos/filebrowser/filebrowser/releases/latest"
                }
            }
        }

# Global configuration
MODULE_CONFIG = load_module_config()

def get_filebrowser_paths():
    """
    Get all Filebrowser-related paths that should be backed up.
    Returns:
        list: List of paths that exist and should be backed up
    """
    paths = []
    config = MODULE_CONFIG["config"]
    
    # Add data directory
    data_dir = config["directories"]["data_dir"]
    if os.path.exists(data_dir):
        paths.append(data_dir)
        log_message(f"Found Filebrowser data directory: {data_dir}")
    
    # Add config directory
    config_dir = config["directories"]["config_dir"]
    if os.path.exists(config_dir):
        paths.append(config_dir)
        log_message(f"Found Filebrowser config directory: {config_dir}")
    
    return paths

def get_filebrowser_version():
    """Detect currently installed Filebrowser version."""
    try:
        result = subprocess.run(["filebrowser", "version"], capture_output=True, text=True, check=False)
        if result.returncode == 0:
            version = result.stdout.strip()
            return version
        return None
    except Exception as e:
        log_message(f"Warning: Failed to detect Filebrowser version: {e}")
        return None

def get_latest_filebrowser_version():
    """
    Get the latest Filebrowser version from GitHub releases.
    Returns:
        str: Latest version string or None
    """
    try:
        api_url = MODULE_CONFIG["config"]["installation"]["github_api_url"]
        with urllib.request.urlopen(api_url) as resp:
            data = json.load(resp)
            tag = data.get("tag_name", "")
            if tag.startswith("v"):
                return tag[1:]
            return tag
    except Exception as e:
        log_message(f"Failed to get latest version info: {e}", "ERROR")
        return None

def verify_filebrowser_installation():
    """
    Verify that Filebrowser is properly installed and functional.
    Returns:
        dict: Verification results with status and details
    """
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
        # Check binary
        bin_path = "/usr/local/bin/filebrowser"
        verification_results["paths"]["binary"] = bin_path
        
        if os.path.exists(bin_path):
            verification_results["binary_exists"] = True
            if os.access(bin_path, os.X_OK):
                verification_results["binary_executable"] = True
                
                # Check version
                version = get_filebrowser_version()
                if version:
                    verification_results["version_readable"] = True
                    verification_results["version"] = version
        
        # Check directories
        config_dir = MODULE_CONFIG["config"]["directories"]["config_dir"]
        data_dir = MODULE_CONFIG["config"]["directories"]["data_dir"]
        
        verification_results["paths"]["config_dir"] = config_dir
        verification_results["paths"]["data_dir"] = data_dir
        
        verification_results["config_dir_exists"] = os.path.exists(config_dir)
        verification_results["data_dir_exists"] = os.path.exists(data_dir)
        
        # Log verification results
        for check, result in verification_results.items():
            if check not in ["version", "paths"]:
                status = "✓" if result else "✗"
                log_message(f"Filebrowser verification - {check}: {status}")
        
        if verification_results["version"]:
            log_message(f"Filebrowser verification - version: {verification_results['version']}")
        
    except Exception as e:
        log_message(f"Error during Filebrowser verification: {e}", "ERROR")
    
    return verification_results

def main(args=None):
    """
    Main entry point for Filebrowser update module.
    Args:
        args: List of arguments (supports '--version', '--check', '--verify', '--config')
    Returns:
        dict: Status and results of the update
    """
    if args is None:
        args = []
    
    # Handle command line arguments first
    if args and len(args) > 0:
        if args[0] == "--version":
            version = get_filebrowser_version()
            if version:
                log_message(f"Detected Filebrowser version: {version}")
                return {"success": True, "version": version}
            else:
                log_message("Could not detect Filebrowser version")
                return {"success": False, "error": "Version detection failed"}
    
    log_message("Starting Filebrowser module update...")
    
    SERVICE_NAME = MODULE_CONFIG["metadata"]["module_name"]
    
    # --config mode: show current configuration
    if len(args) > 0 and args[0] == "--config":
        log_message("Current Filebrowser module configuration:")
        log_message(f"  Data dir: {MODULE_CONFIG['config']['directories']['data_dir']}")
        log_message(f"  Config dir: {MODULE_CONFIG['config']['directories']['config_dir']}")
        
        return {
            "success": True,
            "config": MODULE_CONFIG,
            "paths": {
                "data_dir": MODULE_CONFIG["config"]["directories"]["data_dir"],
                "config_dir": MODULE_CONFIG["config"]["directories"]["config_dir"]
            }
        }

    # --verify mode: comprehensive installation verification
    if len(args) > 0 and args[0] == "--verify":
        log_message("Running comprehensive Filebrowser verification...")
        verification = verify_filebrowser_installation()
        
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
        version = get_filebrowser_version()
        if version:
            log_message(f"OK - Current version: {version}")
            return {"success": True, "version": version}
        else:
            log_message("Filebrowser binary not found", "ERROR")
            return {"success": False, "error": "Not found"}

    # Get current version
    current_version = get_filebrowser_version()
    if not current_version:
        log_message("Failed to get current version of Filebrowser", "ERROR")
        return {"success": False, "error": "No current version"}
    log_message(f"Current Filebrowser version: {current_version}")

    # Get latest version
    latest_version = get_latest_filebrowser_version()
    if not latest_version:
        log_message("Failed to get latest version information", "ERROR")
        return {"success": False, "error": "No latest version"}
    log_message(f"Latest available version: {latest_version}")

    # Compare and update if needed
    if current_version != latest_version:
        log_message("Update available. Creating comprehensive backup...")
        
        # Initialize StateManager with default backup directory
        state_manager = StateManager("/var/backups/updates")
        
        # Get all Filebrowser-related paths for comprehensive backup
        files_to_backup = get_filebrowser_paths()
        
        if not files_to_backup:
            log_message("No Filebrowser files found for backup", "WARNING")
            return {"success": False, "error": "No files to backup"}
        
        log_message(f"Creating backup for {len(files_to_backup)} Filebrowser paths...")
        
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
            # Download and run the installation script
            install_url = "https://raw.githubusercontent.com/filebrowser/get/master/get.sh"
            result = subprocess.run(
                f"curl -fsSL {install_url} | bash",
                shell=True,
                capture_output=True,
                text=True,
                check=False
            )
            
            if result.returncode != 0:
                raise Exception(f"Installation failed: {result.stderr}")
            
            # Verify new installation
            log_message("Verifying new installation...")
            verification = verify_filebrowser_installation()
            new_version = verification.get("version")
            
            if new_version == latest_version:
                log_message(f"Successfully updated Filebrowser from {current_version} to {latest_version}")
                
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
                restored_version = get_filebrowser_version()
                log_message(f"Restored version: {restored_version}")
            else:
                log_message("Failed to restore from backup", "ERROR")
            
            return {
                "success": False, 
                "error": str(e),
                "rollback_success": rollback_success,
                "restored_version": get_filebrowser_version() if rollback_success else None,
                "config": MODULE_CONFIG
            }
    else:
        log_message(f"Filebrowser is already at the latest version ({current_version})")
        
        # Still run verification to ensure everything is working
        verification = verify_filebrowser_installation()
        
        return {
            "success": True, 
            "updated": False, 
            "version": current_version,
            "verification": verification,
            "config": MODULE_CONFIG
        }

if __name__ == "__main__":
    main()
