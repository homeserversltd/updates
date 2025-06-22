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
import json
import subprocess
import shutil
import requests
from pathlib import Path
from typing import Dict, Any, Optional, List
import urllib.request
import tempfile
from updates.index import log_message
from updates.utils.state_manager import StateManager
from updates.utils.permissions import restore_service_permissions_simple, PermissionManager, PermissionTarget

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
                "module_name": "gogs"
            },
            "config": {
                "directories": {
                    "data_dir": "/var/lib/gogs",
                    "config_dir": "/etc/gogs",
                    "install_dir": "/opt/gogs",
                    "config_file": "/opt/gogs/custom/conf/app.ini",
                    "repo_path": "/mnt/nas/git/repositories",
                    "gogs_bin": "/opt/gogs/gogs"
                },
                "installation": {
                    "github_api_url": "https://api.github.com/repos/gogs/gogs/releases/latest",
                    "download_url_template": "https://dl.gogs.io/{version}/gogs_{version}_linux_amd64.tar.gz",
                    "extract_path": "/opt/"
                },
                "permissions": {
                    "owner": "git",
                    "group": "git",
                    "mode": "750"
                }
            }
        }

# Global configuration
MODULE_CONFIG = load_module_config()

def get_gogs_paths():
    """
    Get all Gogs-related paths that should be backed up.
    Returns:
        list: List of paths that exist and should be backed up
    """
    paths = []
    config = MODULE_CONFIG["config"]
    
    # Add all configured directories
    for key, dir_config in config["directories"].items():
        # Handle both new format (dict with path) and legacy format (string)
        path = dir_config["path"] if isinstance(dir_config, dict) else dir_config
        
        if os.path.exists(path):
            paths.append(path)
            log_message(f"Found Gogs path for backup: {path}")
        else:
            log_message(f"Gogs path not found (skipping): {path}", "DEBUG")
    
    return paths

def get_gogs_version():
    """Detect currently installed Gogs version."""
    try:
        gogs_bin_config = MODULE_CONFIG["config"]["directories"]["gogs_bin"]
        bin_path = gogs_bin_config["path"] if isinstance(gogs_bin_config, dict) else gogs_bin_config
        if not os.path.isfile(bin_path) or not os.access(bin_path, os.X_OK):
            return None
        
        result = subprocess.run([bin_path, "--version"], capture_output=True, text=True, check=False)
        if result.returncode == 0:
            # Output format: "Gogs version X.Y.Z"
            version_parts = result.stdout.strip().split()
            if len(version_parts) >= 3 and version_parts[1] == "version":
                return version_parts[2]
        return None
    except Exception as e:
        log_message(f"Warning: Failed to detect Gogs version: {e}")
        return None

def get_latest_gogs_version():
    """
    Get the latest Gogs version from GitHub releases.
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

def verify_gogs_installation():
    """
    Verify that Gogs is properly installed and functional.
    Returns:
        dict: Verification results with status and details
    """
    verification_results = {
        "binary_exists": False,
        "binary_executable": False,
        "version_readable": False,
        "config_dir_exists": False,
        "data_dir_exists": False,
        "install_dir_exists": False,
        "version": None,
        "paths": {}
    }
    
    try:
        # Check binary
        gogs_bin_config = MODULE_CONFIG["config"]["directories"]["gogs_bin"]
        bin_path = gogs_bin_config["path"] if isinstance(gogs_bin_config, dict) else gogs_bin_config
        verification_results["paths"]["binary"] = bin_path
        
        if os.path.exists(bin_path):
            verification_results["binary_exists"] = True
            if os.access(bin_path, os.X_OK):
                verification_results["binary_executable"] = True
                
                # Check version
                version = get_gogs_version()
                if version:
                    verification_results["version_readable"] = True
                    verification_results["version"] = version
        
        # Check directories
        for dir_key, dir_config in MODULE_CONFIG["config"]["directories"].items():
            dir_path = dir_config["path"] if isinstance(dir_config, dict) else dir_config
            verification_results[f"{dir_key}_exists"] = os.path.exists(dir_path)
            verification_results["paths"][dir_key] = dir_path
        
        # Log verification results
        for check, result in verification_results.items():
            if check not in ["version", "paths"]:
                status = "✓" if result else "✗"
                log_message(f"Gogs verification - {check}: {status}")
        
        if verification_results["version"]:
            log_message(f"Gogs verification - version: {verification_results['version']}")
        
    except Exception as e:
        log_message(f"Error during Gogs verification: {e}", "ERROR")
    
    return verification_results

def install_gogs_binary(version):
    """
    Install Gogs from pre-compiled binary.
    Args:
        version: Version to install
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        download_url = MODULE_CONFIG["config"]["installation"]["binary_download_url_template"].format(version=version)
        extract_path = MODULE_CONFIG["config"]["installation"]["extract_path"]
        
        log_message(f"Attempting binary installation from {download_url}")
        
        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as temp_file:
            log_message(f"Downloading {download_url}...")
            urllib.request.urlretrieve(download_url, temp_file.name)
            
            # Extract to temporary location first
            temp_extract = tempfile.mkdtemp()
            subprocess.run(["tar", "xzf", temp_file.name, "-C", temp_extract], check=True)
            
            # Move to final location
            gogs_dir = os.path.join(temp_extract, "gogs")
            install_dir_config = MODULE_CONFIG["config"]["directories"]["install_dir"]
            install_dir = install_dir_config["path"] if isinstance(install_dir_config, dict) else install_dir_config
            
            if os.path.exists(install_dir):
                shutil.rmtree(install_dir)
            shutil.move(gogs_dir, install_dir)
            
            # Clean up
            os.unlink(temp_file.name)
            shutil.rmtree(temp_extract)
            
            log_message("Binary installation completed successfully")
            return True
            
    except Exception as e:
        log_message(f"Binary installation failed: {e}", "WARNING")
        return False

def install_gogs_from_source(version):
    """
    Install Gogs by building from source.
    Args:
        version: Version to build
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Hardcoded source build configuration
        repo_url = MODULE_CONFIG["config"]["installation"]["source_repo_url"]
        build_dir = "/tmp/gogs_build"
        build_command = ["make", "build"]
        build_timeout = 600
        
        install_dir_config = MODULE_CONFIG["config"]["directories"]["install_dir"]
        install_dir = install_dir_config["path"] if isinstance(install_dir_config, dict) else install_dir_config
        
        log_message(f"Attempting source build for version {version}")
        
        # Clean up any existing build directory
        if os.path.exists(build_dir):
            shutil.rmtree(build_dir)
        
        # Clone the repository
        log_message(f"Cloning repository {repo_url}")
        subprocess.run([
            "git", "clone", "--depth", "1", "--branch", f"v{version}",
            repo_url, build_dir
        ], check=True, timeout=120)
        
        # Change to build directory
        original_cwd = os.getcwd()
        os.chdir(build_dir)
        
        try:
            # Check Go version
            go_version_result = subprocess.run(["go", "version"], capture_output=True, text=True, check=True)
            log_message(f"Using Go: {go_version_result.stdout.strip()}")
            
            # Build Gogs
            log_message("Building Gogs from source...")
            subprocess.run(build_command, check=True, timeout=build_timeout)
            
            # Install the built binary
            if os.path.exists(install_dir):
                shutil.rmtree(install_dir)
            os.makedirs(install_dir, exist_ok=True)
            
            # Copy built binary and other necessary files
            built_binary = os.path.join(build_dir, "gogs")
            gogs_bin_config = MODULE_CONFIG["config"]["directories"]["gogs_bin"]
            target_binary = gogs_bin_config["path"] if isinstance(gogs_bin_config, dict) else gogs_bin_config
            
            if os.path.exists(built_binary):
                shutil.copy2(built_binary, target_binary)
                os.chmod(target_binary, 0o755)
                log_message("Source build completed successfully")
                return True
            else:
                log_message("Built binary not found", "ERROR")
                return False
                
        finally:
            os.chdir(original_cwd)
            # Clean up build directory
            if os.path.exists(build_dir):
                shutil.rmtree(build_dir)
                
    except subprocess.TimeoutExpired:
        log_message("Source build timed out", "ERROR")
        return False
    except Exception as e:
        log_message(f"Source build failed: {e}", "WARNING")
        return False

def restore_gogs_permissions():
    """
    Restore proper ownership and permissions for Gogs files and directories.
    This is critical after updates that run as root to prevent service failures.
    
    Returns:
        bool: True if permissions were restored successfully, False otherwise
    """
    try:
        log_message("Restoring Gogs permissions after update...")
        
        config = MODULE_CONFIG["config"]
        permission_manager = PermissionManager("gogs")
        
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
                
                # Determine if it's a directory or file and if recursive
                is_directory = os.path.isdir(path) if os.path.exists(path) else "dir" in dir_key
                recursive = is_directory and dir_key in ["install_dir", "repo_path", "data_dir", "config_dir"]
                
                targets.append(PermissionTarget(
                    path=path,
                    owner=owner,
                    group=default_group,
                    mode=mode,
                    recursive=recursive
                ))
            else:
                # Legacy format fallback
                targets.append(PermissionTarget(
                    path=dir_config,
                    owner=default_owner,
                    group=default_group,
                    mode=0o755,
                    recursive=True
                ))
        
        success = permission_manager.set_permissions(targets)
        
        if success:
            log_message("Successfully restored Gogs permissions")
        else:
            log_message("Failed to restore some Gogs permissions", "WARNING")
            
        return success
        
    except Exception as e:
        log_message(f"Critical error during Gogs permission restoration: {e}", "ERROR")
        return False

def main(args=None):
    """
    Main entry point for Gogs update module.
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
            version = get_gogs_version()
            if version:
                log_message(f"Detected Gogs version: {version}")
                return {"success": True, "version": version}
            else:
                log_message("Could not detect Gogs version")
                return {"success": False, "error": "Version detection failed"}
        elif args[0] == "--fix-permissions":
            log_message("Manually restoring Gogs permissions...")
            if restore_gogs_permissions():
                log_message("✓ Permissions restored successfully")
                return {"success": True, "message": "Permissions restored"}
            else:
                log_message("✗ Failed to restore permissions")
                return {"success": False, "error": "Permission restoration failed"}
    
    log_message("Starting Gogs module update...")
    
    SERVICE_NAME = MODULE_CONFIG["metadata"]["module_name"]
    
    # --config mode: show current configuration
    if len(args) > 0 and args[0] == "--config":
        log_message("Current Gogs module configuration:")
        for key, dir_config in MODULE_CONFIG["config"]["directories"].items():
            path = dir_config["path"] if isinstance(dir_config, dict) else dir_config
            log_message(f"  {key}: {path}")
        
        return {
            "success": True,
            "config": MODULE_CONFIG,
            "paths": {k: (v["path"] if isinstance(v, dict) else v) for k, v in MODULE_CONFIG["config"]["directories"].items()}
        }

    # --verify mode: comprehensive installation verification
    if len(args) > 0 and args[0] == "--verify":
        log_message("Running comprehensive Gogs verification...")
        verification = verify_gogs_installation()
        
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
        version = get_gogs_version()
        if version:
            log_message(f"OK - Current version: {version}")
            return {"success": True, "version": version}
        else:
            log_message("Gogs binary not found", "ERROR")
            return {"success": False, "error": "Not found"}

    # Get current version
    current_version = get_gogs_version()
    if not current_version:
        log_message("Failed to get current version of Gogs", "ERROR")
        return {"success": False, "error": "No current version"}
    log_message(f"Current Gogs version: {current_version}")

    # Get latest version
    latest_version = get_latest_gogs_version()
    if not latest_version:
        log_message("Failed to get latest version information", "ERROR")
        return {"success": False, "error": "No latest version"}
    log_message(f"Latest available version: {latest_version}")

    # Compare and update if needed
    if current_version != latest_version:
        log_message("Update available. Creating comprehensive backup...")
        
        # Initialize state manager
        state_manager = StateManager()
        
        # Get all Gogs-related paths for comprehensive backup
        files_to_backup = get_gogs_paths()
        
        if not files_to_backup:
            log_message("No Gogs files found for backup", "WARNING")
            return {"success": False, "error": "No files to backup"}
        
        log_message(f"Creating backup for {len(files_to_backup)} Gogs paths...")
        
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
            # Try binary installation first
            success = install_gogs_binary(latest_version)
            
            # If binary installation fails and fallback is enabled, try source build
            if not success and MODULE_CONFIG["config"]["installation"].get("fallback_to_source", False):
                log_message("Binary installation failed, attempting source build...")
                success = install_gogs_from_source(latest_version)
            
            if not success:
                raise Exception("Both binary and source installation methods failed")
            
            # Restore permissions using the centralized permission system
            restore_gogs_permissions()
            
            # Verify new installation
            log_message("Verifying new installation...")
            verification = verify_gogs_installation()
            new_version = verification.get("version")
            
            if new_version == latest_version:
                log_message(f"Successfully updated Gogs from {current_version} to {latest_version}")
                
                # Run post-update verification
                if not verification["binary_executable"] or not verification["version_readable"]:
                    raise Exception("Post-update verification failed - installation appears incomplete")
                
                # Restore Gogs permissions
                restore_gogs_permissions()
                
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
                restored_version = get_gogs_version()
                log_message(f"Restored version: {restored_version}")
            else:
                log_message("Failed to restore from backup", "ERROR")
            
            return {
                "success": False, 
                "error": str(e),
                "rollback_success": rollback_success,
                "restored_version": get_gogs_version() if rollback_success else None,
                "config": MODULE_CONFIG
            }
    else:
        log_message(f"Gogs is already at the latest version ({current_version})")
        
        # Still run verification to ensure everything is working
        verification = verify_gogs_installation()
        
        return {
            "success": True, 
            "updated": False, 
            "version": current_version,
            "verification": verification,
            "config": MODULE_CONFIG
        }

if __name__ == "__main__":
    main()
