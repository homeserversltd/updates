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
import json
import time
import urllib.request
from ...index import log_message
from ...utils.state_manager import StateManager

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
                "service": {
                    "name": "filebrowser",
                    "systemd_service": "filebrowser"
                },
                "directories": {
                    "bin_path": "/usr/local/bin/filebrowser",
                    "data_dir": "/etc/filebrowser",
                    "db_path": "/etc/filebrowser/filebrowser.db",
                    "settings_path": "/etc/filebrowser/settings.json"
                },
                "backup": {
                    "backup_dir": "/var/backups/updates",
                    "include_paths": [
                        "/usr/local/bin/filebrowser"
                    ]
                },
                "installation": {
                    "install_script_url": "https://raw.githubusercontent.com/filebrowser/get/master/get.sh",
                    "github_api_url": "https://api.github.com/repos/filebrowser/filebrowser/releases/latest"
                }
            }
        }

# Global configuration
MODULE_CONFIG = load_module_config()

def get_backup_config():
    """
    Get backup configuration from module config.
    Returns:
        dict: Backup configuration
    """
    return MODULE_CONFIG["config"]["backup"]

def get_installation_config():
    """
    Get installation configuration from module config.
    Returns:
        dict: Installation configuration
    """
    return MODULE_CONFIG["config"]["installation"]

def get_service_config():
    """
    Get service configuration from module config.
    Returns:
        dict: Service configuration
    """
    return MODULE_CONFIG["config"]["service"]

def get_directories_config():
    """
    Get directories configuration from module config.
    Returns:
        dict: Directories configuration
    """
    return MODULE_CONFIG["config"]["directories"]

# --- Service management ---
def systemctl(action, service):
    """Execute systemctl command for a service."""
    try:
        result = subprocess.run(["systemctl", action, service], capture_output=True, text=True)
        if result.returncode != 0:
            log_message(f"systemctl {action} {service} failed: {result.stderr}", "ERROR")
            return False
        return True
    except Exception as e:
        log_message(f"systemctl {action} {service} error: {e}", "ERROR")
        return False

def is_service_active(service):
    """Check if a systemd service is active."""
    try:
        result = subprocess.run(["systemctl", "is-active", "--quiet", service])
        return result.returncode == 0
    except Exception:
        return False

# --- Version helpers ---
def get_current_version():
    """
    Get the current version of Filebrowser if installed.
    Returns:
        str: Version string or None if not installed
    """
    try:
        bin_path = get_directories_config()["bin_path"]
        if not os.path.isfile(bin_path) or not os.access(bin_path, os.X_OK):
            return None
        
        result = subprocess.run([bin_path, "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            # Output: 'File Browser v2.23.0' or similar
            for line in result.stdout.splitlines():
                if "v" in line:
                    parts = line.strip().split()
                    for part in parts:
                        if part.startswith("v") and part[1:].replace(".", "").isdigit():
                            return part[1:]
            # Fallback: third word
            parts = result.stdout.strip().split()
            if len(parts) >= 3:
                return parts[2].lstrip("v")
        return None
    except Exception:
        return None

def get_latest_version():
    """
    Get the latest Filebrowser version from GitHub releases using configured URL.
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

def install_filebrowser():
    """
    Install/update Filebrowser using the configured installation script.
    Returns:
        bool: True if install succeeded, False otherwise
    """
    log_message("Installing/updating Filebrowser...", "INFO")
    try:
        install_url = get_installation_config()["install_script_url"]
        result = subprocess.run(
            f"curl -fsSL {install_url} | bash",
            shell=True, capture_output=True, text=True
        )
        if result.returncode == 0:
            log_message("Filebrowser installation successful", "INFO")
            return True
        else:
            log_message(f"Filebrowser installation failed: {result.stderr}", "ERROR")
            return False
    except Exception as e:
        log_message(f"Error during Filebrowser installation: {str(e)}", "ERROR")
        return False

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
        "service_active": False,
        "version": None,
        "paths": {}
    }
    
    try:
        # Check binary
        bin_path = get_directories_config()["bin_path"]
        service_name = get_service_config()["systemd_service"]
        
        verification_results["paths"]["binary"] = bin_path
        
        if os.path.exists(bin_path):
            verification_results["binary_exists"] = True
            if os.access(bin_path, os.X_OK):
                verification_results["binary_executable"] = True
                
                # Check version
                version = get_current_version()
                if version:
                    verification_results["version_readable"] = True
                    verification_results["version"] = version
        
        # Check service status
        verification_results["service_active"] = is_service_active(service_name)
        
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
        args: List of arguments (supports '--check', '--verify', '--config')
    Returns:
        dict: Status and results of the update
    """
    if args is None:
        args = []
    
    SERVICE_NAME = MODULE_CONFIG["metadata"]["module_name"]
    service_config = get_service_config()
    directories_config = get_directories_config()
    
    BIN_PATH = directories_config["bin_path"]
    SYSTEMD_SERVICE = service_config["systemd_service"]

    # --config mode: show current configuration
    if len(args) > 0 and args[0] == "--config":
        log_message("Current Filebrowser module configuration:")
        log_message(f"  Binary path: {BIN_PATH}")
        log_message(f"  Service name: {SYSTEMD_SERVICE}")
        log_message(f"  Data dir: {directories_config['data_dir']}")
        
        backup_config = get_backup_config()
        log_message(f"  Backup dir: {backup_config['backup_dir']}")
        log_message(f"  Backup paths: {backup_config['include_paths']}")
        
        return {
            "success": True,
            "config": MODULE_CONFIG,
            "paths": directories_config
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
        version = get_current_version()
        if version:
            log_message(f"OK - Current version: {version}")
            return {"success": True, "version": version}
        else:
            log_message(f"Filebrowser binary not found at {BIN_PATH}", "ERROR")
            return {"success": False, "error": "Not found"}

    # Get current version
    current_version = get_current_version()
    if not current_version:
        log_message("Failed to get current version of Filebrowser", "ERROR")
        return {"success": False, "error": "No current version"}
    log_message(f"Current Filebrowser version: {current_version}")

    # Get latest version
    latest_version = get_latest_version()
    if not latest_version:
        log_message("Failed to get latest version information", "ERROR")
        return {"success": False, "error": "No latest version"}
    log_message(f"Latest available version: {latest_version}")

    # Compare and update if needed
    if current_version != latest_version:
        log_message("Update available. Creating backup...")
        
        # Initialize global rollback system with configured backup directory
        backup_config = get_backup_config()
        state_manager = StateManager(backup_config["backup_dir"])
        
        # Get files to backup from configuration
        files_to_backup = []
        for path in backup_config["include_paths"]:
            if os.path.exists(path):
                files_to_backup.append(path)
                log_message(f"Found Filebrowser file for backup: {path}")
            else:
                log_message(f"Filebrowser file not found (skipping): {path}", "DEBUG")
        
        if not files_to_backup:
            log_message("No Filebrowser files found for backup", "WARNING")
            return {"success": False, "error": "No files to backup"}
        
        log_message(f"Creating backup for {len(files_to_backup)} Filebrowser files...")
        
        # Create rollback point
        rollback_point = state_manager.create_rollback_point(
            module_name=SERVICE_NAME,
            description=f"pre_update_{current_version}_to_{latest_version}",
            files=files_to_backup
        )
        
        if not rollback_point:
            log_message("Failed to create rollback point", "ERROR")
            return {"success": False, "error": "Backup failed"}
        
        log_message(f"Rollback point created with {len(rollback_point)} backups")
        
        # Stop service before update
        log_message("Stopping Filebrowser service...")
        systemctl("stop", SYSTEMD_SERVICE)
        
        # Perform the update
        log_message("Installing update...")
        try:
            if not install_filebrowser():
                raise Exception("Filebrowser installation failed")
            
            # Start service after update
            log_message("Starting Filebrowser service...")
            systemctl("start", SYSTEMD_SERVICE)
            
            # Wait for service to start
            time.sleep(5)
            
            # Verify new installation
            log_message("Verifying new installation...")
            verification = verify_filebrowser_installation()
            new_version = verification.get("version")
            
            if new_version == latest_version and verification["service_active"]:
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
                    "rollback_point": rollback_point,
                    "config": MODULE_CONFIG
                }
            else:
                if new_version != latest_version:
                    raise Exception(f"Version mismatch after update. Expected: {latest_version}, Got: {new_version}")
                else:
                    raise Exception("Service failed to start after update")
                
        except Exception as e:
            log_message(f"Update failed: {e}", "ERROR")
            log_message("Restoring from rollback point...")
            
            # Restore rollback point
            rollback_success = state_manager.restore_rollback_point(rollback_point)
            
            if rollback_success:
                log_message("Successfully restored from rollback point")
                # Start service after rollback
                systemctl("start", SYSTEMD_SERVICE)
                # Verify rollback worked
                restored_version = get_current_version()
                log_message(f"Restored version: {restored_version}")
            else:
                log_message("Failed to restore from rollback point", "ERROR")
            
            return {
                "success": False, 
                "error": str(e),
                "rollback_success": rollback_success,
                "rollback_point": rollback_point,
                "restored_version": get_current_version() if rollback_success else None,
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
