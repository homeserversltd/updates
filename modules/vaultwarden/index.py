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
import shutil
import tarfile
import urllib.request
import json
import time
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
                "module_name": "vaultwarden"
            },
            "config": {
                "service": {
                    "name": "vaultwarden",
                    "user": "vaultwarden",
                    "group": "vaultwarden"
                },
                "directories": {
                    "binary_path": "/opt/vaultwarden/vaultwarden",
                    "web_vault_dir": "/opt/vaultwarden/web-vault",
                    "data_dir": "/var/lib/vaultwarden",
                    "log_dir": "/var/log/vaultwarden",
                    "attachments_dir": "/mnt/nas/vaultwarden/attachments",
                    "config_file": "/etc/vaultwarden.env",
                    "cargo_home": "/usr/local/cargo",
                    "cargo_bin": "~/.cargo/bin/vaultwarden"
                },
                "backup": {
                    "backup_dir": "/var/backups/updates",
                    "max_age_days": 30,
                    "keep_minimum": 5,
                    "include_paths": [
                        "/opt/vaultwarden/vaultwarden",
                        "/opt/vaultwarden/web-vault",
                        "/var/lib/vaultwarden",
                        "/etc/vaultwarden.env",
                        "/var/log/vaultwarden",
                        "/mnt/nas/vaultwarden/attachments"
                    ]
                },
                "installation": {
                    "main_repo": {
                        "github_api_url": "https://api.github.com/repos/dani-garcia/vaultwarden/releases/latest",
                        "cargo_package": "vaultwarden",
                        "cargo_features": ["postgresql"]
                    },
                    "web_vault": {
                        "github_api_url": "https://api.github.com/repos/dani-garcia/bw_web_builds/releases/latest",
                        "download_template": "https://github.com/dani-garcia/bw_web_builds/releases/download/{version}/bw_web_{version}.tar.gz"
                    },
                    "temp_dir": "/tmp"
                },
                "verification": {
                    "startup_wait_seconds": 5,
                    "version_check_retries": 3
                }
            }
        }

# Global configuration
MODULE_CONFIG = load_module_config()

def get_service_config():
    """Get service configuration from module config."""
    return MODULE_CONFIG["config"]["service"]

def get_directories_config():
    """Get directories configuration from module config."""
    return MODULE_CONFIG["config"]["directories"]

def get_backup_config():
    """Get backup configuration from module config."""
    return MODULE_CONFIG["config"]["backup"]

def get_installation_config():
    """Get installation configuration from module config."""
    return MODULE_CONFIG["config"]["installation"]

def get_verification_config():
    """Get verification configuration from module config."""
    return MODULE_CONFIG["config"]["verification"]

def get_existing_backup_paths():
    """
    Get all Vaultwarden-related paths that exist and should be backed up.
    Returns:
        list: List of existing paths to backup
    """
    backup_config = get_backup_config()
    include_paths = backup_config["include_paths"]
    
    existing_paths = []
    for path in include_paths:
        if os.path.exists(path):
            existing_paths.append(path)
            log_message(f"Found Vaultwarden path for backup: {path}")
        else:
            log_message(f"Vaultwarden path not found (skipping): {path}", "DEBUG")
    
    return existing_paths

# --- Service management ---
def systemctl(action, service):
    """Execute systemctl command for service management."""
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
    Get the current version of Vaultwarden if installed.
    Returns:
        str: Version string or None if not installed
    """
    try:
        directories = get_directories_config()
        binary_path = directories["binary_path"]
        
        if not os.path.isfile(binary_path) or not os.access(binary_path, os.X_OK):
            return None
            
        result = subprocess.run([binary_path, "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            # Parse version from output
            for line in result.stdout.splitlines():
                parts = line.strip().split()
                for part in parts:
                    if part[0].isdigit() and part.count('.') == 2:
                        return part
            # Fallback parsing
            parts = result.stdout.strip().split()
            if len(parts) >= 2:
                return parts[1].lstrip("v")
        return None
    except Exception:
        return None

def get_latest_version():
    """
    Get the latest Vaultwarden version from GitHub releases.
    Returns:
        str: Latest version string or None
    """
    try:
        installation_config = get_installation_config()
        api_url = installation_config["main_repo"]["github_api_url"]
        
        with urllib.request.urlopen(api_url) as resp:
            data = json.load(resp)
            tag = data.get("tag_name", "")
            if tag.startswith("v"):
                return tag[1:]
            return tag
    except Exception as e:
        log_message(f"Failed to get latest version info: {e}", "ERROR")
        return None

def get_latest_web_version():
    """
    Get the latest web vault version from GitHub releases.
    Returns:
        str: Latest web vault version string or None
    """
    try:
        installation_config = get_installation_config()
        api_url = installation_config["web_vault"]["github_api_url"]
        
        with urllib.request.urlopen(api_url) as resp:
            data = json.load(resp)
            tag = data.get("tag_name", "")
            return tag
    except Exception as e:
        log_message(f"Failed to get latest web vault version info: {e}", "ERROR")
        return None

# --- Update logic ---
def update_vaultwarden():
    """
    Update Vaultwarden binary and web vault using configured settings.
    Returns:
        bool: True if update succeeded, False otherwise
    """
    directories = get_directories_config()
    installation_config = get_installation_config()
    service_config = get_service_config()
    
    # Install new version using cargo
    log_message("Installing new version with Cargo...")
    try:
        env = os.environ.copy()
        env["CARGO_HOME"] = directories["cargo_home"]
        env["PATH"] = f"{directories['cargo_home']}/bin:" + env.get("PATH", "")
        
        cargo_features = installation_config["main_repo"]["cargo_features"]
        cargo_package = installation_config["main_repo"]["cargo_package"]
        
        cmd = ["cargo", "install", cargo_package, "--features", ",".join(cargo_features)]
        result = subprocess.run(cmd, env=env, capture_output=True, text=True)
        
        if result.returncode != 0:
            log_message(f"Failed to build/install vaultwarden: {result.stderr}", "ERROR")
            return False
            
    except Exception as e:
        log_message(f"Error during cargo install: {e}", "ERROR")
        return False
    
    # Copy binary to system location
    try:
        cargo_bin_path = os.path.expanduser(directories["cargo_bin"])
        system_bin_path = directories["binary_path"]
        
        shutil.copy2(cargo_bin_path, system_bin_path)
        os.chmod(system_bin_path, 0o755)
        
        # Set ownership
        user = service_config["user"]
        group = service_config["group"]
        subprocess.run(["chown", f"{user}:{group}", system_bin_path])
        
        log_message(f"Binary copied to {system_bin_path}")
        
    except Exception as e:
        log_message(f"Failed to copy binary to system location: {e}", "ERROR")
        return False
    
    # Update web vault
    log_message("Updating web vault...")
    latest_web_version = get_latest_web_version()
    if not latest_web_version:
        log_message("Failed to get latest web vault version", "ERROR")
        return False
    
    try:
        web_vault_dir = directories["web_vault_dir"]
        temp_dir = installation_config["temp_dir"]
        download_template = installation_config["web_vault"]["download_template"]
        
        # Remove existing web vault
        if os.path.exists(web_vault_dir):
            shutil.rmtree(web_vault_dir)
        os.makedirs(web_vault_dir, exist_ok=True)
        
        # Download and extract web vault
        tarball_url = download_template.format(version=latest_web_version)
        tarball_path = os.path.join(temp_dir, "web_vault.tar.gz")
        
        result = subprocess.run(["curl", "-L", tarball_url, "-o", tarball_path])
        if result.returncode != 0:
            log_message("Failed to download web vault", "ERROR")
            return False
        
        with tarfile.open(tarball_path, "r:gz") as tar:
            tar.extractall(web_vault_dir)
        
        # Cleanup temp file
        os.remove(tarball_path)
        
        # Set ownership
        user = service_config["user"]
        group = service_config["group"]
        subprocess.run(["chown", "-R", f"{user}:{group}", web_vault_dir])
        
        log_message(f"Web vault updated to version {latest_web_version}")
        
    except Exception as e:
        log_message(f"Failed to update web vault: {e}", "ERROR")
        return False
    
    return True

def verify_vaultwarden_installation():
    """
    Verify that Vaultwarden is properly installed and functional.
    Returns:
        dict: Verification results with status and details
    """
    verification_results = {
        "binary_exists": False,
        "binary_executable": False,
        "version_readable": False,
        "web_vault_exists": False,
        "data_dir_exists": False,
        "config_file_exists": False,
        "service_active": False,
        "version": None,
        "paths": {}
    }
    
    try:
        directories = get_directories_config()
        service_config = get_service_config()
        
        # Check binary
        binary_path = directories["binary_path"]
        verification_results["paths"]["binary"] = binary_path
        
        if os.path.exists(binary_path):
            verification_results["binary_exists"] = True
            if os.access(binary_path, os.X_OK):
                verification_results["binary_executable"] = True
                
                # Check version
                version = get_current_version()
                if version:
                    verification_results["version_readable"] = True
                    verification_results["version"] = version
        
        # Check other components
        web_vault_dir = directories["web_vault_dir"]
        data_dir = directories["data_dir"]
        config_file = directories["config_file"]
        
        verification_results["paths"]["web_vault_dir"] = web_vault_dir
        verification_results["paths"]["data_dir"] = data_dir
        verification_results["paths"]["config_file"] = config_file
        
        verification_results["web_vault_exists"] = os.path.exists(web_vault_dir)
        verification_results["data_dir_exists"] = os.path.exists(data_dir)
        verification_results["config_file_exists"] = os.path.exists(config_file)
        
        # Check service status
        service_name = service_config["name"]
        verification_results["service_active"] = is_service_active(service_name)
        
        # Log verification results
        for check, result in verification_results.items():
            if check not in ["version", "paths"]:
                status = "✓" if result else "✗"
                log_message(f"Vaultwarden verification - {check}: {status}")
        
        if verification_results["version"]:
            log_message(f"Vaultwarden verification - version: {verification_results['version']}")
        
    except Exception as e:
        log_message(f"Error during Vaultwarden verification: {e}", "ERROR")
    
    return verification_results

def main(args=None):
    """
    Main entry point for Vaultwarden update module.
    Args:
        args: List of arguments (supports '--check', '--verify', '--config')
    Returns:
        dict: Status and results of the update
    """
    if args is None:
        args = []
    
    service_config = get_service_config()
    directories = get_directories_config()
    SERVICE_NAME = service_config["name"]
    VAULTWARDEN_BIN = directories["binary_path"]

    # --config mode: show current configuration
    if len(args) > 0 and args[0] == "--config":
        log_message("Current Vaultwarden module configuration:")
        log_message(f"  Service: {SERVICE_NAME}")
        log_message(f"  Binary path: {VAULTWARDEN_BIN}")
        log_message(f"  Web vault dir: {directories['web_vault_dir']}")
        log_message(f"  Data dir: {directories['data_dir']}")
        log_message(f"  Config file: {directories['config_file']}")
        
        backup_config = get_backup_config()
        log_message(f"  Backup dir: {backup_config['backup_dir']}")
        log_message(f"  Max age: {backup_config['max_age_days']} days")
        log_message(f"  Keep minimum: {backup_config['keep_minimum']} backups")
        
        return {
            "success": True,
            "config": MODULE_CONFIG,
            "service": SERVICE_NAME,
            "paths": directories
        }

    # --verify mode: comprehensive installation verification
    if len(args) > 0 and args[0] == "--verify":
        log_message("Running comprehensive Vaultwarden verification...")
        verification = verify_vaultwarden_installation()
        
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
            log_message(f"Vaultwarden binary not found at {VAULTWARDEN_BIN}", "ERROR")
            return {"success": False, "error": "Not found"}

    # Get current version
    current_version = get_current_version()
    if not current_version:
        log_message("Failed to get current version of Vaultwarden", "ERROR")
        return {"success": False, "error": "No current version"}
    log_message(f"Current Vaultwarden version: {current_version}")

    # Get latest version
    latest_version = get_latest_version()
    if not latest_version:
        log_message("Failed to get latest version information", "ERROR")
        return {"success": False, "error": "No latest version"}
    log_message(f"Latest available version: {latest_version}")

    # Compare and update if needed
    if current_version != latest_version:
        log_message("Update available. Creating comprehensive backup...")
        
        # Initialize StateManager with backup directory
        backup_config = get_backup_config()
        state_manager = StateManager(backup_config["backup_dir"])
        
        # Get all existing Vaultwarden paths for backup
        files_to_backup = get_existing_backup_paths()
        
        if not files_to_backup:
            log_message("No Vaultwarden files found for backup", "WARNING")
            return {"success": False, "error": "No files to backup"}
        
        log_message(f"Creating backup for {len(files_to_backup)} Vaultwarden paths...")
        
        # Stop service before backup and update
        log_message(f"Stopping {SERVICE_NAME} service...")
        systemctl("stop", SERVICE_NAME)
        
        # Create comprehensive backup using StateManager
        backup_success = state_manager.backup_module_state(
            module_name=SERVICE_NAME,
            description=f"pre_update_{current_version}_to_{latest_version}",
            files=files_to_backup,
            services=[SERVICE_NAME]
        )
        
        if not backup_success:
            log_message("Failed to create backup", "ERROR")
            systemctl("start", SERVICE_NAME)  # Restart service on backup failure
            return {"success": False, "error": "Backup failed"}
        
        log_message("Backup created successfully")
        
        # Perform the update
        log_message("Installing update...")
        try:
            if not update_vaultwarden():
                raise Exception("Vaultwarden update failed")
            
            # Start service
            log_message(f"Starting {SERVICE_NAME} service...")
            systemctl("start", SERVICE_NAME)
            
            # Wait for service to start
            verification_config = get_verification_config()
            wait_time = verification_config["startup_wait_seconds"]
            log_message(f"Waiting {wait_time} seconds for service to start...")
            time.sleep(wait_time)
            
            # Verify new installation
            log_message("Verifying new installation...")
            verification = verify_vaultwarden_installation()
            new_version = verification.get("version")
            
            if new_version == latest_version and verification["service_active"]:
                log_message(f"Successfully updated Vaultwarden from {current_version} to {latest_version}")
                
                return {
                    "success": True, 
                    "updated": True, 
                    "old_version": current_version, 
                    "new_version": new_version,
                    "verification": verification,
                    "backup_created": True,
                    "config": MODULE_CONFIG
                }
            else:
                raise Exception(f"Post-update verification failed. Version: {new_version}, Service active: {verification['service_active']}")
                
        except Exception as e:
            log_message(f"Update failed: {e}", "ERROR")
            log_message("Restoring from backup...")
            
            # Stop service before restore
            systemctl("stop", SERVICE_NAME)
            
            # Restore using StateManager
            restore_success = state_manager.restore_module_state(SERVICE_NAME)
            
            # Start service after restore
            systemctl("start", SERVICE_NAME)
            
            if restore_success:
                log_message("Successfully restored from backup")
                # Verify restore worked
                restored_version = get_current_version()
                log_message(f"Restored version: {restored_version}")
            else:
                log_message("Failed to restore from backup", "ERROR")
            
            return {
                "success": False, 
                "error": str(e),
                "restore_success": restore_success,
                "restored_version": get_current_version() if restore_success else None,
                "config": MODULE_CONFIG
            }
    else:
        log_message(f"Vaultwarden is already at the latest version ({current_version})")
        
        # Still run verification to ensure everything is working
        verification = verify_vaultwarden_installation()
        
        return {
            "success": True, 
            "updated": False, 
            "version": current_version,
            "verification": verification,
            "config": MODULE_CONFIG
        }

if __name__ == "__main__":
    main()
