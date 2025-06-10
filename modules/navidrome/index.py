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
import tarfile
import urllib.request
from ...index import log_message
from ...utils.global_rollback import GlobalRollback

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
                "service": {
                    "name": "navidrome",
                    "systemd_service": "navidrome"
                },
                "directories": {
                    "install_dir": "/opt/navidrome",
                    "data_dir": "/var/lib/navidrome",
                    "navidrome_bin": "/opt/navidrome/navidrome",
                    "config_file": "/var/lib/navidrome/navidrome.toml"
                },
                "backup": {
                    "backup_dir": "/var/backups/updates",
                    "include_paths": [
                        "/opt/navidrome/navidrome",
                        "/var/lib/navidrome"
                    ]
                },
                "installation": {
                    "github_api_url": "https://api.github.com/repos/navidrome/navidrome/releases/latest",
                    "download_url_template": "https://github.com/navidrome/navidrome/releases/download/v{version}/navidrome_{version}_linux_amd64.tar.gz",
                    "extract_path": "/opt/navidrome/"
                },
                "permissions": {
                    "owner": "navidrome",
                    "group": "navidrome",
                    "mode": "755"
                }
            }
        }

# Global configuration
MODULE_CONFIG = load_module_config()

def get_backup_config():
    """Get backup configuration from module config."""
    return MODULE_CONFIG["config"]["backup"]

def get_installation_config():
    """Get installation configuration from module config."""
    return MODULE_CONFIG["config"]["installation"]

def get_service_config():
    """Get service configuration from module config."""
    return MODULE_CONFIG["config"]["service"]

def get_directories_config():
    """Get directories configuration from module config."""
    return MODULE_CONFIG["config"]["directories"]

def get_permissions_config():
    """Get permissions configuration from module config."""
    return MODULE_CONFIG["config"]["permissions"]

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
    Get the current version of Navidrome if installed.
    Returns:
        str: Version string or None if not installed
    """
    try:
        navidrome_bin = get_directories_config()["navidrome_bin"]
        if not os.path.isfile(navidrome_bin) or not os.access(navidrome_bin, os.X_OK):
            return None
        
        result = subprocess.run([navidrome_bin, "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            # Output: 'Navidrome v0.49.3' or similar
            for line in result.stdout.splitlines():
                parts = line.strip().split()
                for part in parts:
                    if part[0].isdigit() and part.count('.') == 2:
                        return part
            # Fallback: third word
            parts = result.stdout.strip().split()
            if len(parts) >= 3:
                return parts[2].lstrip("v")
        return None
    except Exception:
        return None

def get_latest_version():
    """
    Get the latest Navidrome version from GitHub releases using configured URL.
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

def set_permissions():
    """Set proper ownership and permissions for Navidrome installation."""
    try:
        dirs_config = get_directories_config()
        perms_config = get_permissions_config()
        install_dir = dirs_config["install_dir"]
        data_dir = dirs_config["data_dir"]
        
        # Set ownership for install directory
        subprocess.run([
            "chown", "-R", 
            f"{perms_config['owner']}:{perms_config['group']}", 
            install_dir
        ], check=True)
        
        # Set ownership for data directory
        subprocess.run([
            "chown", "-R", 
            f"{perms_config['owner']}:{perms_config['group']}", 
            data_dir
        ], check=True)
        
        # Set permissions for binary
        navidrome_bin = dirs_config["navidrome_bin"]
        subprocess.run([
            "chmod", perms_config["mode"], navidrome_bin
        ], check=True)
        
        log_message(f"Set permissions on {install_dir} and {data_dir}")
        return True
    except Exception as e:
        log_message(f"Failed to set permissions: {e}", "WARNING")
        return False

def install_navidrome(version):
    """
    Download and install Navidrome using configured settings.
    Args:
        version: Version to install
    Returns:
        bool: True if install succeeded, False otherwise
    """
    log_message(f"Installing Navidrome {version}...", "INFO")
    try:
        install_config = get_installation_config()
        dirs_config = get_directories_config()
        
        # Build download URL
        download_url = install_config["download_url_template"].format(version=version)
        tarball_path = "/tmp/navidrome.tar.gz"
        
        # Download
        log_message(f"Downloading from {download_url}...")
        result = subprocess.run(["wget", "-q", download_url, "-O", tarball_path])
        if result.returncode != 0:
            log_message("Failed to download new version", "ERROR")
            return False
        
        # Create install directory if it doesn't exist
        install_dir = dirs_config["install_dir"]
        os.makedirs(install_dir, exist_ok=True)
        
        # Extract new version (overwrites existing binary)
        with tarfile.open(tarball_path, "r:gz") as tar:
            tar.extractall(install_config["extract_path"])
        
        os.remove(tarball_path)
        log_message("Extracted new version")
        
        # Set permissions
        set_permissions()
        
        return True
        
    except Exception as e:
        log_message(f"Error during Navidrome installation: {str(e)}", "ERROR")
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
        "version": None,
        "paths": {}
    }
    
    try:
        dirs_config = get_directories_config()
        service_config = get_service_config()
        
        navidrome_bin = dirs_config["navidrome_bin"]
        data_dir = dirs_config["data_dir"]
        service_name = service_config["systemd_service"]
        
        verification_results["paths"]["binary"] = navidrome_bin
        verification_results["paths"]["data_dir"] = data_dir
        
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
        verification_results["service_active"] = is_service_active(service_name)
        
        # Log verification results
        for check, result in verification_results.items():
            if check not in ["version", "paths"]:
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
    
    SERVICE_NAME = MODULE_CONFIG["metadata"]["module_name"]
    service_config = get_service_config()
    directories_config = get_directories_config()
    
    NAVIDROME_BIN = directories_config["navidrome_bin"]
    SYSTEMD_SERVICE = service_config["systemd_service"]

    # --config mode: show current configuration
    if len(args) > 0 and args[0] == "--config":
        log_message("Current Navidrome module configuration:")
        log_message(f"  Binary path: {NAVIDROME_BIN}")
        log_message(f"  Service name: {SYSTEMD_SERVICE}")
        log_message(f"  Install dir: {directories_config['install_dir']}")
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
        log_message("Update available. Creating backup...")
        
        # Initialize global rollback system with configured backup directory
        backup_config = get_backup_config()
        rollback = GlobalRollback(backup_config["backup_dir"])
        
        # Get files to backup from configuration
        files_to_backup = []
        for path in backup_config["include_paths"]:
            if os.path.exists(path):
                files_to_backup.append(path)
                log_message(f"Found Navidrome file for backup: {path}")
            else:
                log_message(f"Navidrome file not found (skipping): {path}", "DEBUG")
        
        if not files_to_backup:
            log_message("No Navidrome files found for backup", "WARNING")
            return {"success": False, "error": "No files to backup"}
        
        log_message(f"Creating backup for {len(files_to_backup)} Navidrome files...")
        
        # Create rollback point
        rollback_point = rollback.create_rollback_point(
            module_name=SERVICE_NAME,
            description=f"pre_update_{current_version}_to_{latest_version}",
            files=files_to_backup
        )
        
        if not rollback_point:
            log_message("Failed to create rollback point", "ERROR")
            return {"success": False, "error": "Backup failed"}
        
        log_message(f"Rollback point created with {len(rollback_point)} backups")
        
        # Stop service before update
        log_message("Stopping Navidrome service...")
        systemctl("stop", SYSTEMD_SERVICE)
        
        # Perform the update
        log_message("Installing update...")
        try:
            if not install_navidrome(latest_version):
                raise Exception("Navidrome installation failed")
            
            # Start service after update
            log_message("Starting Navidrome service...")
            systemctl("start", SYSTEMD_SERVICE)
            
            # Wait for service to start
            time.sleep(5)
            
            # Verify new installation
            log_message("Verifying new installation...")
            verification = verify_navidrome_installation()
            new_version = verification.get("version")
            
            if new_version == latest_version and verification["service_active"]:
                log_message(f"Successfully updated Navidrome from {current_version} to {latest_version}")
                
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
            rollback_success = rollback.restore_rollback_point(rollback_point)
            
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
