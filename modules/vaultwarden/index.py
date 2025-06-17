#!/usr/bin/env python3
"""
Vaultwarden Update Module for HOMESERVER

This module handles updating Vaultwarden password manager.
Vaultwarden is typically built from source using Cargo.

Features:
- Multi-method version detection (web vault files, git, Cargo.toml, binary)
- Comprehensive backup and restore using StateManager
- Service management integration
- Installation verification

Author: HOMESERVER Development Team
License: BSL -> GPL (3-year grace period)
"""

import os
import sys
import json
import subprocess
import time
import urllib.request
import shutil
import tempfile
import tarfile
import re

# Add the parent directory to the path to import StateManager
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.state_manager import StateManager

def log_message(message, level="INFO"):
    """Log a message with timestamp and level."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}")

def load_module_config():
    """Load module configuration from index.json."""
    try:
        config_path = os.path.join(os.path.dirname(__file__), "index.json")
        with open(config_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        log_message(f"Failed to load module config: {e}", "ERROR")
        return {
            "metadata": {
                "schema_version": "1.0.3",
                "module_name": "vaultwarden",
                "description": "Vaultwarden password manager",
                "enabled": True
            },
            "config": {
                "directories": {
                    "install_dir": "/opt/vaultwarden",
                    "binary_path": "/opt/vaultwarden/vaultwarden",
                    "web_vault_dir": "/opt/vaultwarden/web-vault",
                    "src_dir": "/opt/vaultwarden/src",
                    "data_dir": "/var/lib/vaultwarden",
                    "config_dir": "/etc/vaultwarden",
                    "log_dir": "/var/log/vaultwarden",
                    "cargo_home": "/usr/local/cargo",
                    "cargo_bin": "~/.cargo/bin/vaultwarden"
                },
                "service": {
                    "name": "vaultwarden",
                    "systemd_service": "vaultwarden",
                    "user": "vaultwarden",
                    "group": "vaultwarden"
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
                }
            }
        }

# Load configuration
MODULE_CONFIG = load_module_config()

def get_service_name():
    """Get service name from module metadata."""
    return MODULE_CONFIG["metadata"]["module_name"]

def get_directories_config():
    """Get directories configuration from module config."""
    return MODULE_CONFIG["config"].get("directories", {
        "install_dir": "/opt/vaultwarden",
        "binary_path": "/opt/vaultwarden/vaultwarden",
        "web_vault_dir": "/opt/vaultwarden/web-vault",
        "src_dir": "/opt/vaultwarden/src",
        "data_dir": "/var/lib/vaultwarden",
        "config_dir": "/etc/vaultwarden",
        "log_dir": "/var/log/vaultwarden",
        "cargo_home": "/usr/local/cargo",
        "cargo_bin": "~/.cargo/bin/vaultwarden"
    })

def get_installation_config():
    """Get installation configuration from module config."""
    return MODULE_CONFIG["config"].get("installation", {
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
    })



def get_all_vaultwarden_paths():
    """
    Get all Vaultwarden-related paths that exist and should be backed up.
    Returns:
        list: List of existing paths to backup
    """
    directories = get_directories_config()
    
    # Standard paths that should be backed up if they exist
    potential_paths = [
        directories["binary_path"],
        directories["web_vault_dir"],
        directories["data_dir"],
        directories["config_dir"],
        directories["log_dir"],
        "/etc/vaultwarden.env",  # Common config file location
        "/mnt/nas/vaultwarden/attachments"  # NAS attachments if configured
    ]
    
    existing_paths = []
    for path in potential_paths:
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
    Uses multiple detection methods based on how vaultwarden is installed.
    Returns:
        str: Version string or None if not installed
    """
    try:
        directories = get_directories_config()
        binary_path = directories["binary_path"]
        
        if not os.path.isfile(binary_path):
            log_message(f"Vaultwarden binary not found at {binary_path}", "DEBUG")
            return None
        
        # Method 1: Try binary version command (most accurate for binary updates)
        try:
            result = subprocess.run([binary_path, "--version"], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                output = result.stdout.strip()
                log_message(f"Binary version output: '{output}'", "DEBUG")
                
                # Handle case where version info is not present
                if "Version info from Git not present" in output:
                    log_message("Binary version info not available from Git", "DEBUG")
                    # Continue to other methods instead of returning unknown
                else:
                    # Try to parse version from output
                    import re
                    version_pattern = r'v?(\d+\.\d+\.\d+)'
                    match = re.search(version_pattern, output)
                    if match:
                        binary_version = match.group(1)
                        log_message(f"Found binary version: {binary_version}", "DEBUG")
                        return binary_version
        except Exception as e:
            log_message(f"Failed to get binary version: {e}", "DEBUG")
        
        # Method 2: Check git repository if it still exists
        src_dir = "/opt/vaultwarden/src"
        if os.path.exists(os.path.join(src_dir, ".git")):
            try:
                result = subprocess.run(
                    ["git", "describe", "--tags", "--always"],
                    cwd=src_dir,
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    git_version = result.stdout.strip()
                    if git_version:
                        log_message(f"Found git version: {git_version}", "DEBUG")
                        return git_version
            except Exception as e:
                log_message(f"Failed to get git version: {e}", "DEBUG")
        
        # Method 3: Check Cargo.toml version
        cargo_toml = os.path.join(src_dir, "Cargo.toml")
        if os.path.exists(cargo_toml):
            try:
                with open(cargo_toml, 'r') as f:
                    for line in f:
                        if line.strip().startswith('version = '):
                            version = line.split('=')[1].strip().strip('"')
                            if version and version != "1.0.0":  # Skip placeholder version
                                log_message(f"Found Cargo.toml version: {version}", "DEBUG")
                                return version
            except Exception as e:
                log_message(f"Failed to read Cargo.toml: {e}", "DEBUG")
        
        # Method 4: Check web vault version files (fallback only)
        web_vault_dir = directories.get("web_vault_dir", "/opt/vaultwarden/web-vault")
        
        # Try vw-version.json first (vaultwarden-specific version)
        vw_version_file = os.path.join(web_vault_dir, "vw-version.json")
        if os.path.exists(vw_version_file):
            try:
                import json
                with open(vw_version_file, 'r') as f:
                    data = json.load(f)
                    version = data.get("version", "").strip()
                    if version:
                        log_message(f"Found vaultwarden version from vw-version.json: {version}", "DEBUG")
                        return version
            except Exception as e:
                log_message(f"Failed to read vw-version.json: {e}", "DEBUG")
        
        # Try version.json (bitwarden web vault version)
        version_file = os.path.join(web_vault_dir, "version.json")
        if os.path.exists(version_file):
            try:
                import json
                with open(version_file, 'r') as f:
                    data = json.load(f)
                    version = data.get("version", "").strip()
                    if version:
                        log_message(f"Found web vault version from version.json: {version}", "DEBUG")
                        return version
            except Exception as e:
                log_message(f"Failed to read version.json: {e}", "DEBUG")
        
        # If we get here, vaultwarden is installed but version is unclear
        log_message("Vaultwarden is installed but version could not be determined", "WARNING")
        return "unknown"
        
    except Exception as e:
        log_message(f"Error getting Vaultwarden version: {e}", "WARNING")
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
            # Remove 'v' prefix if present
            return tag.lstrip('v') if tag else None
    except Exception as e:
        log_message(f"Failed to get latest Vaultwarden version: {e}", "ERROR")
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
            # Remove 'v' prefix if present
            return tag.lstrip('v') if tag else None
    except Exception as e:
        log_message(f"Failed to get latest web vault version: {e}", "ERROR")
        return None

def update_vaultwarden():
    """
    Update Vaultwarden by building from source and updating web vault.
    Returns:
        bool: True if update successful
    """
    try:
        directories = get_directories_config()
        installation_config = get_installation_config()
        
        # Get latest versions
        latest_version = get_latest_version()
        latest_web_version = get_latest_web_version()
        
        if not latest_version or not latest_web_version:
            log_message("Failed to get latest version information", "ERROR")
            return False
        
        log_message(f"Updating to Vaultwarden {latest_version} with web vault {latest_web_version}")
        
        # Create temporary directory
        temp_dir = tempfile.mkdtemp(prefix="vaultwarden_update_")
        
        try:
            # Clone or update source repository
            src_dir = os.path.join(temp_dir, "vaultwarden")
            log_message("Cloning Vaultwarden repository...")
            
            result = subprocess.run([
                "git", "clone", "--depth", "1", "--branch", latest_version,
                "https://github.com/dani-garcia/vaultwarden.git", src_dir
            ], capture_output=True, text=True)
            
            if result.returncode != 0:
                log_message(f"Failed to clone repository: {result.stderr}", "ERROR")
                return False
            
            # Build Vaultwarden
            log_message("Building Vaultwarden...")
            cargo_features = installation_config["main_repo"]["cargo_features"]
            features_arg = f"--features={','.join(cargo_features)}" if cargo_features else ""
            
            # Use full path to cargo binary
            cargo_home = directories.get("cargo_home", "/usr/local/cargo")
            cargo_bin = os.path.join(cargo_home, "bin", "cargo")
            
            build_cmd = [cargo_bin, "build", "--release"]
            if features_arg:
                build_cmd.append(features_arg)
            
            # Set up environment for cargo build
            build_env = os.environ.copy()
            build_env["CARGO_HOME"] = cargo_home
            
            result = subprocess.run(build_cmd, cwd=src_dir, capture_output=True, text=True, env=build_env)
            
            if result.returncode != 0:
                log_message(f"Failed to build Vaultwarden: {result.stderr}", "ERROR")
                return False
            
            # Install new binary
            built_binary = os.path.join(src_dir, "target", "release", "vaultwarden")
            target_binary = directories["binary_path"]
            
            if not os.path.exists(built_binary):
                log_message(f"Built binary not found at {built_binary}", "ERROR")
                return False
            
            log_message("Installing new binary...")
            shutil.copy2(built_binary, target_binary)
            os.chmod(target_binary, 0o755)
            
            # Download and install web vault
            log_message("Downloading web vault...")
            web_vault_url = installation_config["web_vault"]["download_template"].format(version=latest_web_version)
            web_vault_archive = os.path.join(temp_dir, f"bw_web_{latest_web_version}.tar.gz")
            
            with urllib.request.urlopen(web_vault_url) as resp:
                with open(web_vault_archive, 'wb') as f:
                    shutil.copyfileobj(resp, f)
            
            # Extract web vault
            log_message("Installing web vault...")
            web_vault_dir = directories["web_vault_dir"]
            
            # Remove old web vault
            if os.path.exists(web_vault_dir):
                shutil.rmtree(web_vault_dir)
            
            # Extract new web vault
            with tarfile.open(web_vault_archive, 'r:gz') as tar:
                tar.extractall(path=os.path.dirname(web_vault_dir))
            
            # The extracted directory might have a different name
            extracted_dir = os.path.join(os.path.dirname(web_vault_dir), "web-vault")
            if os.path.exists(extracted_dir):
                shutil.move(extracted_dir, web_vault_dir)
            
            log_message("Vaultwarden update completed successfully")
            return True
            
        finally:
            # Clean up temporary directory
            shutil.rmtree(temp_dir, ignore_errors=True)
            
    except Exception as e:
        log_message(f"Error during Vaultwarden update: {e}", "ERROR")
        return False

def verify_vaultwarden_installation():
    """
    Verify Vaultwarden installation is working correctly.
    Returns:
        dict: Verification results
    """
    verification_results = {
        "binary_exists": False,
        "binary_executable": False,
        "version_readable": False,
        "web_vault_exists": False,
        "service_active": False,
        "version": None
    }
    
    try:
        directories = get_directories_config()
        
        binary_path = directories["binary_path"]
        web_vault_dir = directories["web_vault_dir"]
        service_name = get_service_name()
        
        # Check binary exists
        verification_results["binary_exists"] = os.path.isfile(binary_path)
        log_message(f"Binary exists: {verification_results['binary_exists']}")
        
        # Check binary is executable
        if verification_results["binary_exists"]:
            verification_results["binary_executable"] = os.access(binary_path, os.X_OK)
            log_message(f"Binary executable: {verification_results['binary_executable']}")
        
        # Check version is readable
        if verification_results["binary_executable"]:
            version = get_current_version()
            verification_results["version_readable"] = version is not None
            verification_results["version"] = version
            log_message(f"Version readable: {verification_results['version_readable']} (version: {version})")
        
        # Check web vault exists
        verification_results["web_vault_exists"] = os.path.isdir(web_vault_dir)
        log_message(f"Web vault exists: {verification_results['web_vault_exists']}")
        
        # Check service is active
        verification_results["service_active"] = is_service_active(service_name)
        log_message(f"Service active: {verification_results['service_active']}")
        
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
    
    directories = get_directories_config()
    SERVICE_NAME = get_service_name()
    VAULTWARDEN_BIN = directories.get("binary_path", "/opt/vaultwarden/vaultwarden")

    # --config mode: show current configuration
    if len(args) > 0 and args[0] == "--config":
        log_message("Current Vaultwarden module configuration:")
        log_message(f"  Service: {SERVICE_NAME}")
        log_message(f"  Binary path: {VAULTWARDEN_BIN}")
        log_message(f"  Web vault dir: {directories['web_vault_dir']}")
        log_message(f"  Data dir: {directories['data_dir']}")
        log_message(f"  Config dir: {directories['config_dir']}")
        
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
        
        # Initialize StateManager with default backup directory
        state_manager = StateManager()  # Use default backup directory
        
        # Get all existing Vaultwarden paths for backup
        files_to_backup = get_all_vaultwarden_paths()
        
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
            wait_time = 5  # Reasonable default wait time
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
