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
import json
import time
import tarfile
import urllib.request
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
        # Return default configuration
        return {
            "metadata": {
                "schema_version": "1.0.0",
                "module_name": "navidrome"
            },
            "config": {
                "directories": {
                    "install_dir": "/opt/navidrome",
                    "data_dir": "/var/lib/navidrome",
                    "navidrome_bin": "/opt/navidrome/navidrome"
                },
                "installation": {
                    "github_api_url": "https://api.github.com/repos/navidrome/navidrome/releases/latest"
                }
            }
        }

# Global configuration
MODULE_CONFIG = load_module_config()

def get_navidrome_paths():
    """
    Get all Navidrome-related paths that should be backed up.
    Returns:
        list: List of paths that exist and should be backed up
    """
    paths = []
    config = MODULE_CONFIG["config"]
    
    # Add all configured directories
    for dir_key, dir_config in config["directories"].items():
        # Handle both new format (dict with path) and legacy format (string)
        path = dir_config["path"] if isinstance(dir_config, dict) else dir_config
        
        if os.path.exists(path):
            paths.append(path)
            log_message(f"Found Navidrome path for backup: {path}")
        else:
            log_message(f"Navidrome path not found (skipping): {path}", "DEBUG")
    
    return paths

def get_installation_config():
    """Get installation configuration from module config."""
    return MODULE_CONFIG["config"].get("installation", {
        "github_api_url": "https://api.github.com/repos/navidrome/navidrome/releases/latest"
    })

# --- Service management ---
def systemctl(action, service="navidrome"):
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

def is_service_active(service="navidrome"):
    """Check if a systemd service is active."""
    try:
        result = subprocess.run(["systemctl", "is-active", "--quiet", service])
        return result.returncode == 0
    except Exception:
        return False

# --- Version helpers ---
def get_current_version():
    """
    Get the current version of Navidrome if installed.
    Returns:
        str: Version string or None if not installed
    """
    try:
        # Handle both new format (dict with path) and legacy format (string)
        navidrome_bin_config = MODULE_CONFIG["config"]["directories"].get("navidrome_bin", "/opt/navidrome/navidrome")
        navidrome_bin = navidrome_bin_config["path"] if isinstance(navidrome_bin_config, dict) else navidrome_bin_config
        
        if not os.path.isfile(navidrome_bin):
            log_message(f"Navidrome binary not found at {navidrome_bin}", "DEBUG")
            return None
        
        if not os.access(navidrome_bin, os.X_OK):
            log_message(f"Navidrome binary not executable at {navidrome_bin}", "DEBUG")
            return None
        
        result = subprocess.run([navidrome_bin, "--version"], capture_output=True, text=True, timeout=10)
        
        if result.returncode != 0:
            log_message(f"Navidrome version command failed with return code {result.returncode}", "DEBUG")
            log_message(f"stderr: {result.stderr}", "DEBUG")
            return None
        
        output = result.stdout.strip()
        log_message(f"Navidrome version output: '{output}'", "DEBUG")
        
        if not output:
            log_message("Navidrome version command returned empty output", "DEBUG")
            return None
        
        # Parse version from output like "0.53.3 (13af8ed4)"
        import re
        version_pattern = r'(\d+\.\d+\.\d+)'
        match = re.search(version_pattern, output)
        if match:
            return match.group(1)
        
        log_message(f"Could not parse version from output: '{output}'", "WARNING")
        return None
        
    except subprocess.TimeoutExpired:
        log_message("Navidrome version command timed out", "WARNING")
        return None
    except Exception as e:
        log_message(f"Error getting Navidrome version: {e}", "WARNING")
        return None

def get_latest_version():
    """
    Get the latest Navidrome version from GitHub releases.
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

def install_navidrome(version):
    """
    Download and install Navidrome.
    Args:
        version: Version to install
    Returns:
        bool: True if install succeeded, False otherwise
    """
    log_message(f"Installing Navidrome {version}...", "INFO")
    try:
        config = MODULE_CONFIG["config"]["directories"]
        install_dir_config = config.get("install_dir", "/opt/navidrome")
        install_dir = install_dir_config["path"] if isinstance(install_dir_config, dict) else install_dir_config
        
        # Build download URL
        download_url = f"https://github.com/navidrome/navidrome/releases/download/v{version}/navidrome_{version}_linux_amd64.tar.gz"
        tarball_path = "/tmp/navidrome.tar.gz"
        
        # Download
        log_message(f"Downloading from {download_url}...")
        result = subprocess.run(["wget", "-q", download_url, "-O", tarball_path])
        if result.returncode != 0:
            log_message("Failed to download new version", "ERROR")
            return False
        
        # Create install directory if it doesn't exist
        os.makedirs(install_dir, exist_ok=True)
        
        # Extract new version (overwrites existing binary)
        with tarfile.open(tarball_path, "r:gz") as tar:
            tar.extractall(install_dir)
        
        os.remove(tarball_path)
        log_message("Extracted new version")
        
        # Restore proper permissions using PermissionManager
        if not restore_navidrome_permissions():
            log_message("Warning: Failed to restore permissions after installation", "WARNING")
        
        return True
        
    except Exception as e:
        log_message(f"Error during Navidrome installation: {str(e)}", "ERROR")
        return False

def restore_navidrome_permissions():
    """
    Restore proper ownership and permissions for navidrome files and directories.
    This is critical after updates that run as root to prevent service failures.
    
    Returns:
        bool: True if permissions were restored successfully, False otherwise
    """
    try:
        log_message("Restoring navidrome permissions after update...")
        
        config = MODULE_CONFIG["config"]
        permission_manager = PermissionManager("navidrome")
        
        # Build permission targets from JSON configuration
        targets = []
        default_owner = config["permissions"]["owner"]
        default_group = config["permissions"]["group"]
        
        for dir_key, dir_config in config["directories"].items():
            if isinstance(dir_config, dict):
                # New format with embedded permissions
                path = dir_config["path"]
                owner = dir_config.get("owner", default_owner)
                mode = int(dir_config["mode"], 8)  # Convert string to octal
                
                # Binary files should be owned by root for security
                if "bin" in dir_key.lower():
                    owner = "root"
                    group = "root"
                else:
                    group = default_group
                
                # Determine if this should be recursive
                recursive = os.path.isdir(path) if os.path.exists(path) else True
                
                targets.append(PermissionTarget(
                    path=path,
                    owner=owner,
                    group=group,
                    mode=mode,
                    recursive=recursive
                ))
            else:
                # Legacy format - use defaults
                targets.append(PermissionTarget(
                    path=dir_config,
                    owner=default_owner,
                    group=default_group,
                    mode=0o755,
                    recursive=True
                ))
        
        # Apply all permission targets
        success = permission_manager.set_permissions(targets)
        
        if success:
            log_message("✓ Successfully restored navidrome permissions")
        else:
            log_message("✗ Failed to restore some navidrome permissions", "WARNING")
        
        return success
        
    except Exception as e:
        log_message(f"Error restoring navidrome permissions: {e}", "ERROR")
        return False

def verify_navidrome_installation():
    """
    Verify that Navidrome is properly installed and functional.
    Returns:
        dict: Verification results with status and details
    """
    verification_results = {
        "binary_exists": False,
        "binary_executable": False,
        "version_readable": False,
        "service_active": False,
        "data_dir_exists": False,
        "version": None
    }
    
    try:
        config = MODULE_CONFIG["config"]["directories"]
        
        # Handle both new format (dict with path) and legacy format (string)
        navidrome_bin_config = config.get("navidrome_bin", "/opt/navidrome/navidrome")
        navidrome_bin = navidrome_bin_config["path"] if isinstance(navidrome_bin_config, dict) else navidrome_bin_config
        
        data_dir_config = config.get("data_dir", "/var/lib/navidrome")
        data_dir = data_dir_config["path"] if isinstance(data_dir_config, dict) else data_dir_config
        
        # Check binary
        if os.path.exists(navidrome_bin):
            verification_results["binary_exists"] = True
            if os.access(navidrome_bin, os.X_OK):
                verification_results["binary_executable"] = True
                
                # Check version
                version = get_current_version()
                if version:
                    verification_results["version_readable"] = True
                    verification_results["version"] = version
        
        # Check data directory
        verification_results["data_dir_exists"] = os.path.exists(data_dir)
        
        # Check service status
        verification_results["service_active"] = is_service_active()
        
        # Log verification results
        for check, result in verification_results.items():
            if check != "version":
                status = "✓" if result else "✗"
                log_message(f"Navidrome verification - {check}: {status}")
        
        if verification_results["version"]:
            log_message(f"Navidrome verification - version: {verification_results['version']}")
        
    except Exception as e:
        log_message(f"Error during Navidrome verification: {e}", "ERROR")
    
    return verification_results

def main(args=None):
    """
    Main entry point for Navidrome update module.
    Args:
        args: List of arguments (supports '--check', '--verify', '--config')
    Returns:
        dict: Status and results of the update
    """
    if args is None:
        args = []
    
    # Module directory for reference
    module_dir = Path(__file__).parent
    
    log_message("Starting Navidrome module update...")
    
    SERVICE_NAME = MODULE_CONFIG["metadata"]["module_name"]
    config = MODULE_CONFIG["config"]["directories"]
    
    # Handle both new format (dict with path) and legacy format (string)
    navidrome_bin_config = config.get("navidrome_bin", "/opt/navidrome/navidrome")
    NAVIDROME_BIN = navidrome_bin_config["path"] if isinstance(navidrome_bin_config, dict) else navidrome_bin_config

    # --fix-permissions mode: restore permissions only
    if len(args) > 0 and args[0] == "--fix-permissions":
        log_message("Restoring Navidrome permissions...")
        success = restore_navidrome_permissions()
        return {
            "success": success,
            "permissions_restored": success
        }

    # --config mode: show current configuration
    if len(args) > 0 and args[0] == "--config":
        log_message("Current Navidrome module configuration:")
        log_message(f"  Binary path: {NAVIDROME_BIN}")
        
        # Handle new directory format
        for dir_key, dir_config in config.items():
            if isinstance(dir_config, dict):
                log_message(f"  {dir_key}: {dir_config['path']}")
            else:
                log_message(f"  {dir_key}: {dir_config}")
        
        state_manager = StateManager()
        log_message(f"  Backup dir: {state_manager.backup_root}")
        
        return {
            "success": True,
            "config": MODULE_CONFIG
        }

    # --verify mode: comprehensive installation verification
    if len(args) > 0 and args[0] == "--verify":
        log_message("Running comprehensive Navidrome verification...")
        verification = verify_navidrome_installation()
        
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
            log_message(f"Navidrome binary not found at {NAVIDROME_BIN}", "ERROR")
            return {"success": False, "error": "Not found"}

    # Get current version
    current_version = get_current_version()
    if not current_version:
        log_message("Failed to get current version of Navidrome", "ERROR")
        return {"success": False, "error": "No current version"}
    log_message(f"Current Navidrome version: {current_version}")

    # Get latest version
    latest_version = get_latest_version()
    if not latest_version:
        log_message("Failed to get latest version information", "ERROR")
        return {"success": False, "error": "No latest version"}
    log_message(f"Latest available version: {latest_version}")

    # Compare and update if needed
    if current_version != latest_version:
        log_message("Update available. Creating comprehensive backup...")
        
        # Initialize StateManager with default backup directory
        state_manager = StateManager()
        
        # Get all Navidrome-related paths for comprehensive backup
        files_to_backup = get_navidrome_paths()
        
        if not files_to_backup:
            log_message("No Navidrome files found for backup", "WARNING")
            return {"success": False, "error": "No files to backup"}
        
        log_message(f"Creating backup for {len(files_to_backup)} Navidrome paths...")
        
        # Create backup using StateManager
        backup_success = state_manager.backup_module_state(
            module_name=SERVICE_NAME,
            description=f"pre_update_{current_version}_to_{latest_version}",
            files=files_to_backup
        )
        
        if not backup_success:
            log_message("Failed to create backup", "ERROR")
            return {"success": False, "error": "Backup failed"}
        
        log_message("Backup created successfully")
        
        # Stop service before update
        log_message("Stopping Navidrome service...")
        systemctl("stop")
        
        # Perform the update
        log_message("Installing update...")
        try:
            if not install_navidrome(latest_version):
                raise Exception("Navidrome installation failed")
            
            # Start service after update
            log_message("Starting Navidrome service...")
            systemctl("start")
            
            # Wait for service to start
            time.sleep(5)
            
            # Verify new installation
            log_message("Verifying new installation...")
            verification = verify_navidrome_installation()
            new_version = verification.get("version")
            
            if new_version == latest_version and verification["service_active"]:
                log_message(f"Successfully updated Navidrome from {current_version} to {latest_version}")
                
                # Restore permissions after successful update
                log_message("Ensuring proper permissions after update...")
                restore_navidrome_permissions()
                
                return {
                    "success": True, 
                    "updated": True, 
                    "old_version": current_version, 
                    "new_version": new_version,
                    "verification": verification,
                    "config": MODULE_CONFIG
                }
            else:
                if new_version != latest_version:
                    raise Exception(f"Version mismatch after update. Expected: {latest_version}, Got: {new_version}")
                else:
                    raise Exception("Service failed to start after update")
                
        except Exception as e:
            log_message(f"Update failed: {e}", "ERROR")
            log_message("Restoring from backup...")
            
            # Restore using StateManager
            rollback_success = state_manager.restore_module_state(SERVICE_NAME)
            
            if rollback_success:
                log_message("Successfully restored from backup")
                # Start service after rollback
                systemctl("start")
                # Verify rollback worked
                restored_version = get_current_version()
                log_message(f"Restored version: {restored_version}")
            else:
                log_message("Failed to restore from backup", "ERROR")
            
            return {
                "success": False, 
                "error": str(e),
                "rollback_success": rollback_success,
                "restored_version": get_current_version() if rollback_success else None,
                "config": MODULE_CONFIG
            }
    else:
        log_message(f"Navidrome is already at the latest version ({current_version})")
        
        # Still run verification to ensure everything is working
        verification = verify_navidrome_installation()
        
        return {
            "success": True, 
            "updated": False, 
            "version": current_version,
            "verification": verification,
            "config": MODULE_CONFIG
        }

if __name__ == "__main__":
    main()
