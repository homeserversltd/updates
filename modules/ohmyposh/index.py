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
import urllib.request
import zipfile
import tempfile
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
                "module_name": "ohmyposh"
            },
            "config": {
                "directories": {
                    "install_dir": "/usr/local/bin",
                    "oh_my_posh_bin": "/usr/local/bin/oh-my-posh",
                    "themes_dir": "/usr/local/share/oh-my-posh/themes"
                },
                "backup": {
                    "backup_dir": "/var/backups/updates",
                    "include_paths": [
                        "/usr/local/bin/oh-my-posh",
                        "/usr/local/share/oh-my-posh"
                    ]
                },
                "installation": {
                    "github_api_url": "https://api.github.com/repos/JanDeDobbeleer/oh-my-posh/releases/latest",
                    "download_url_template": "https://github.com/JanDeDobbeleer/oh-my-posh/releases/download/v{version}/posh-linux-amd64",
                    "themes_url": "https://github.com/JanDeDobbeleer/oh-my-posh/archive/refs/heads/main.zip"
                },
                "permissions": {
                    "binary_mode": "755",
                    "themes_mode": "644"
                }
            }
        }

# Global configuration
MODULE_CONFIG = load_module_config()

def get_backup_config():
    """Get backup configuration from module config."""
    return MODULE_CONFIG["config"].get("backup", {
        "backup_dir": "/var/backups/updates",
        "include_paths": [
            "/usr/local/bin/oh-my-posh",
            "/etc/ohmyposh"
        ]
    })

def get_installation_config():
    """Get installation configuration from module config."""
    return MODULE_CONFIG["config"].get("installation", {
        "github_api_url": "https://api.github.com/repos/JanDeDobbeleer/oh-my-posh/releases/latest",
        "download_url_template": "https://github.com/JanDeDobbeleer/oh-my-posh/releases/download/v{version}/posh-linux-amd64",
        "themes_url": "https://github.com/JanDeDobbeleer/oh-my-posh/archive/main.zip"
    })

def get_directories_config():
    """Get directories configuration from module config."""
    return MODULE_CONFIG["config"].get("directories", {
        "install_dir": "/usr/local/bin",
        "config_dir": "/etc/ohmyposh",
        "oh_my_posh_bin": "/usr/local/bin/oh-my-posh",
        "themes_dir": "/etc/ohmyposh/themes"
    })

def get_directory_path(config, key, default_path):
    """Helper function to get directory path from either new or legacy format."""
    dir_config = config.get(key, default_path)
    return dir_config["path"] if isinstance(dir_config, dict) else dir_config

def get_permissions_config():
    """Get permissions configuration from module config."""
    return MODULE_CONFIG["config"].get("permissions", {
        "binary_mode": "755",
        "themes_mode": "644"
    })

# --- Version helpers ---
def get_current_version():
    """
    Get the current version of Oh My Posh if installed.
    Returns:
        str: Version string or None if not installed
    """
    try:
        directories = get_directories_config()
        oh_my_posh_bin = get_directory_path(directories, "oh_my_posh_bin", "/usr/local/bin/oh-my-posh")
        if not os.path.isfile(oh_my_posh_bin):
            log_message(f"Oh My Posh binary not found at {oh_my_posh_bin}", "DEBUG")
            return None
        
        if not os.access(oh_my_posh_bin, os.X_OK):
            log_message(f"Oh My Posh binary not executable at {oh_my_posh_bin}", "DEBUG")
            return None
        
        result = subprocess.run([oh_my_posh_bin, "--version"], capture_output=True, text=True, timeout=10)
        
        if result.returncode != 0:
            log_message(f"Oh My Posh version command failed with return code {result.returncode}", "DEBUG")
            log_message(f"stderr: {result.stderr}", "DEBUG")
            return None
        
        output = result.stdout.strip()
        log_message(f"Oh My Posh version output: '{output}'", "DEBUG")
        
        if not output:
            log_message("Oh My Posh version command returned empty output", "DEBUG")
            return None
        
        # Parse version - output should be just "24.16.1" or similar
        import re
        version_pattern = r'v?(\d+\.\d+\.\d+)'
        match = re.search(version_pattern, output)
        if match:
            return match.group(1)
        
        # If it's already a clean version number, return as-is
        if re.match(r'^\d+\.\d+\.\d+$', output):
            return output
        
        log_message(f"Could not parse version from output: '{output}'", "WARNING")
        return None
        
    except subprocess.TimeoutExpired:
        log_message("Oh My Posh version command timed out", "WARNING")
        return None
    except Exception as e:
        log_message(f"Error getting Oh My Posh version: {e}", "WARNING")
        return None

def get_latest_version():
    """
    Get the latest Oh My Posh version from GitHub releases using configured URL.
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

def restore_ohmyposh_permissions():
    """
    Restore proper ownership and permissions for oh-my-posh files and directories.
    This is critical after updates that run as root to prevent access issues.
    
    Returns:
        bool: True if permissions were restored successfully, False otherwise
    """
    try:
        log_message("Restoring oh-my-posh permissions after update...")
        
        config = MODULE_CONFIG["config"]
        permission_manager = PermissionManager("ohmyposh")
        
        # Build permission targets from JSON configuration
        targets = []
        default_owner = config["permissions"]["owner"]
        default_group = config["permissions"]["group"]
        
        for dir_key, dir_config in config["directories"].items():
            if isinstance(dir_config, dict):
                # New format with embedded permissions
                path = dir_config["path"]
                owner = dir_config.get("owner", default_owner)
                group = default_group
                mode = int(dir_config["mode"], 8)  # Convert string to octal
                
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
            log_message("✓ Successfully restored oh-my-posh permissions")
        else:
            log_message("✗ Failed to restore some oh-my-posh permissions", "WARNING")
        
        return success
        
    except Exception as e:
        log_message(f"Error restoring oh-my-posh permissions: {e}", "ERROR")
        return False

def install_oh_my_posh_binary(version):
    """
    Download and install Oh My Posh binary.
    Args:
        version: Version to install
    Returns:
        bool: True if install succeeded, False otherwise
    """
    try:
        install_config = get_installation_config()
        dirs_config = get_directories_config()
        
        # Build download URL
        download_url = install_config["download_url_template"].format(version=version)
        oh_my_posh_bin = get_directory_path(dirs_config, "oh_my_posh_bin", "/usr/local/bin/oh-my-posh")
        
        # Download binary
        log_message(f"Downloading Oh My Posh binary from {download_url}...")
        result = subprocess.run(["wget", "-q", download_url, "-O", oh_my_posh_bin])
        if result.returncode != 0:
            log_message("Failed to download Oh My Posh binary", "ERROR")
            return False
        
        log_message("Downloaded Oh My Posh binary")
        return True
        
    except Exception as e:
        log_message(f"Error downloading Oh My Posh binary: {str(e)}", "ERROR")
        return False

def install_oh_my_posh_themes():
    """
    Download and install Oh My Posh themes.
    Returns:
        bool: True if install succeeded, False otherwise
    """
    try:
        install_config = get_installation_config()
        dirs_config = get_directories_config()
        
        themes_url = install_config["themes_url"]
        themes_dir = get_directory_path(dirs_config, "themes_dir", "/etc/ohmyposh/themes")
        
        # Create themes directory
        os.makedirs(themes_dir, exist_ok=True)
        
        # Download themes archive
        with tempfile.TemporaryDirectory() as temp_dir:
            zip_path = os.path.join(temp_dir, "themes.zip")
            
            log_message(f"Downloading Oh My Posh themes from {themes_url}...")
            result = subprocess.run(["wget", "-q", themes_url, "-O", zip_path])
            if result.returncode != 0:
                log_message("Failed to download Oh My Posh themes", "ERROR")
                return False
            
            # Extract themes
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # Extract only the themes directory
                for member in zip_ref.namelist():
                    if member.startswith("oh-my-posh-main/themes/") and member.endswith(".omp.json"):
                        # Extract to themes directory with just the filename
                        filename = os.path.basename(member)
                        if filename:
                            zip_ref.extract(member, temp_dir)
                            extracted_path = os.path.join(temp_dir, member)
                            target_path = os.path.join(themes_dir, filename)
                            os.rename(extracted_path, target_path)
            
            log_message(f"Installed Oh My Posh themes to {themes_dir}")
            return True
        
    except Exception as e:
        log_message(f"Error installing Oh My Posh themes: {str(e)}", "ERROR")
        return False

def install_oh_my_posh(version):
    """
    Install Oh My Posh binary and themes.
    Args:
        version: Version to install
    Returns:
        bool: True if install succeeded, False otherwise
    """
    log_message(f"Installing Oh My Posh {version}...", "INFO")
    
    # Install binary
    if not install_oh_my_posh_binary(version):
        return False
    
    # Install themes
    if not install_oh_my_posh_themes():
        return False
    
    # Restore proper permissions using PermissionManager
    if not restore_ohmyposh_permissions():
        log_message("Warning: Failed to restore permissions after installation", "WARNING")
    
    return True

def verify_oh_my_posh_installation():
    """
    Verify that Oh My Posh is properly installed and functional.
    Returns:
        dict: Verification results with status and details
    """
    verification_results = {
        "binary_exists": False,
        "binary_executable": False,
        "version_readable": False,
        "themes_dir_exists": False,
        "themes_count": 0,
        "version": None,
        "paths": {}
    }
    
    try:
        dirs_config = get_directories_config()
        
        oh_my_posh_bin = get_directory_path(dirs_config, "oh_my_posh_bin", "/usr/local/bin/oh-my-posh")
        themes_dir = get_directory_path(dirs_config, "themes_dir", "/etc/ohmyposh/themes")
        
        verification_results["paths"]["binary"] = oh_my_posh_bin
        verification_results["paths"]["themes_dir"] = themes_dir
        
        # Check binary
        if os.path.exists(oh_my_posh_bin):
            verification_results["binary_exists"] = True
            if os.access(oh_my_posh_bin, os.X_OK):
                verification_results["binary_executable"] = True
                
                # Check version
                version = get_current_version()
                if version:
                    verification_results["version_readable"] = True
                    verification_results["version"] = version
        
        # Check themes directory
        if os.path.exists(themes_dir):
            verification_results["themes_dir_exists"] = True
            # Count theme files
            theme_files = [f for f in os.listdir(themes_dir) if f.endswith('.omp.json')]
            verification_results["themes_count"] = len(theme_files)
        
        # Log verification results
        for check, result in verification_results.items():
            if check not in ["version", "paths", "themes_count"]:
                status = "✓" if result else "✗"
                log_message(f"Oh My Posh verification - {check}: {status}")
        
        if verification_results["version"]:
            log_message(f"Oh My Posh verification - version: {verification_results['version']}")
        
        if verification_results["themes_count"] > 0:
            log_message(f"Oh My Posh verification - themes: {verification_results['themes_count']} found")
        
    except Exception as e:
        log_message(f"Error during Oh My Posh verification: {e}", "ERROR")
    
    return verification_results

def main(args=None):
    """
    Main entry point for Oh My Posh update module.
    Args:
        args: List of arguments (supports '--check', '--verify', '--config')
    Returns:
        dict: Status and results of the update
    """
    if args is None:
        args = []
    
    # Module directory for reference
    module_dir = Path(__file__).parent
    
    SERVICE_NAME = MODULE_CONFIG.get("metadata", {}).get("module_name", "ohmyposh")
    directories_config = get_directories_config()
    
    OH_MY_POSH_BIN = get_directory_path(directories_config, "oh_my_posh_bin", "/usr/local/bin/oh-my-posh")

    # --fix-permissions mode: restore permissions only
    if len(args) > 0 and args[0] == "--fix-permissions":
        log_message("Restoring Oh My Posh permissions...")
        success = restore_ohmyposh_permissions()
        return {
            "success": success,
            "permissions_restored": success
        }

    # --config mode: show current configuration
    if len(args) > 0 and args[0] == "--config":
        log_message("Current Oh My Posh module configuration:")
        log_message(f"  Binary path: {OH_MY_POSH_BIN}")
        
        # Handle new directory format
        for dir_key, dir_config in directories_config.items():
            if isinstance(dir_config, dict):
                log_message(f"  {dir_key}: {dir_config['path']}")
            else:
                log_message(f"  {dir_key}: {dir_config}")
        
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
        log_message("Running comprehensive Oh My Posh verification...")
        verification = verify_oh_my_posh_installation()
        
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
            log_message(f"Oh My Posh binary not found at {OH_MY_POSH_BIN}", "ERROR")
            return {"success": False, "error": "Not found"}

    # Get current version
    current_version = get_current_version()
    if not current_version:
        log_message("Failed to get current version of Oh My Posh", "ERROR")
        return {"success": False, "error": "No current version"}
    log_message(f"Current Oh My Posh version: {current_version}")

    # Get latest version
    latest_version = get_latest_version()
    if not latest_version:
        log_message("Failed to get latest version information", "ERROR")
        return {"success": False, "error": "No latest version"}
    log_message(f"Latest available version: {latest_version}")

    # Compare and update if needed
    if current_version != latest_version:
        log_message("Update available. Creating backup...")
        
        # Initialize StateManager for backup
        state_manager = StateManager()
        
        # Get files to backup from configuration
        backup_config = get_backup_config()
        files_to_backup = []
        for path in backup_config["include_paths"]:
            if os.path.exists(path):
                files_to_backup.append(path)
                log_message(f"Found Oh My Posh file for backup: {path}")
            else:
                log_message(f"Oh My Posh file not found (skipping): {path}", "DEBUG")
        
        if not files_to_backup:
            log_message("No Oh My Posh files found for backup", "WARNING")
            return {"success": False, "error": "No files to backup"}
        
        log_message(f"Creating backup for {len(files_to_backup)} Oh My Posh files...")
        
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
        
        # Perform the update (no service to stop for Oh My Posh)
        log_message("Installing update...")
        try:
            if not install_oh_my_posh(latest_version):
                raise Exception("Oh My Posh installation failed")
            
            # Verify new installation
            log_message("Verifying new installation...")
            verification = verify_oh_my_posh_installation()
            new_version = verification.get("version")
            
            if new_version == latest_version:
                log_message(f"Successfully updated Oh My Posh from {current_version} to {latest_version}")
                
                # Run post-update verification
                if not verification["binary_executable"] or not verification["version_readable"]:
                    raise Exception("Post-update verification failed - installation appears incomplete")
                
                # Restore permissions after successful update
                log_message("Ensuring proper permissions after update...")
                restore_ohmyposh_permissions()
                
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
            
            # Restore using StateManager
            rollback_success = state_manager.restore_module_state(SERVICE_NAME)
            
            if rollback_success:
                log_message("Successfully restored from backup")
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
        log_message(f"Oh My Posh is already at the latest version ({current_version})")
        
        # Still run verification to ensure everything is working
        verification = verify_oh_my_posh_installation()
        
        return {
            "success": True, 
            "updated": False, 
            "version": current_version,
            "verification": verification,
            "config": MODULE_CONFIG
        }

if __name__ == "__main__":
    main()
