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
import sys
import hashlib
import shutil

# Handle imports for both direct execution and module execution
try:
    from updates.index import log_message
    from updates.utils.state_manager import StateManager
except ImportError:
    # Add parent directory to path for direct execution
    parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    try:
        from updates.index import log_message
        from updates.utils.state_manager import StateManager
    except ImportError:
        # Fallback: try adding the current directory to path
        current_dir = os.path.abspath(os.path.dirname(__file__))
        updates_dir = os.path.abspath('/usr/local/lib/updates')
        if updates_dir not in sys.path:
            sys.path.insert(0, updates_dir)
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
                "module_name": "venvs"
            },
            "config": {
                "virtual_environments": {},
                "verification": {
                    "check_activation_script": True,
                    "verify_packages": True,
                    "timeout_seconds": 300
                }
            }
        }

# Global configuration
MODULE_CONFIG = load_module_config()

def get_venvs_config():
    """Get virtual environments configuration from module config."""
    return MODULE_CONFIG["config"]["virtual_environments"]

def get_verification_config():
    """Get verification configuration from module config."""
    return MODULE_CONFIG["config"]["verification"]

def calculate_file_sha256(file_path):
    """Calculate SHA256 hash of a file."""
    try:
        if not os.path.exists(file_path):
            return None
        
        hash_sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()
    except Exception as e:
        log_message(f"Failed to calculate SHA256 for {file_path}: {e}", "ERROR")
        return None

def get_requirements_file_path(venv_name):
    """Get the path to the requirements file for a virtual environment."""
    module_dir = Path(__file__).parent
    src_dir = module_dir / "src"
    requirements_file = src_dir / f"{venv_name}.txt"
    return requirements_file

def get_target_requirements_path(venv_path):
    """Get the path to the requirements.txt file in the parent directory of the venv."""
    # Strip /venv from the path to get the parent directory
    parent_dir = venv_path.replace('/venv', '')
    requirements_file = os.path.join(parent_dir, 'requirements.txt')
    return requirements_file

def check_venv_needs_update(venv_name, venv_cfg):
    """
    Check if a virtual environment needs updating by comparing requirements file SHA256.
    
    Returns:
        Tuple[bool, str, str]: (needs_update, source_sha256, target_sha256)
    """
    try:
        venv_path = venv_cfg["path"]
        requirements_source = venv_cfg.get("requirements_source")
        
        # If no requirements source, skip
        if not requirements_source:
            log_message(f"No requirements source for {venv_name}, skipping", "DEBUG")
            return False, None, None
        
        # If venv doesn't exist, it needs creation
        if not os.path.isdir(venv_path):
            log_message(f"Virtual environment {venv_name} doesn't exist, needs creation", "INFO")
            return True, None, None
        
        # Get source requirements file SHA256 (from src/ folder)
        source_file = get_requirements_file_path(venv_name)
        if not source_file.exists():
            log_message(f"Requirements file {source_file} not found for {venv_name}", "WARNING")
            return False, None, None
        
        source_sha256 = calculate_file_sha256(source_file)
        if not source_sha256:
            log_message(f"Failed to calculate SHA256 for source file {source_file}", "WARNING")
            return False, None, None
        
        # Get target requirements file SHA256 (from parent directory of venv)
        target_file = get_target_requirements_path(venv_path)
        if not os.path.exists(target_file):
            log_message(f"Target requirements file {target_file} not found for {venv_name}", "WARNING")
            return True  # Target file missing, assume update needed
        
        target_sha256 = calculate_file_sha256(target_file)
        if not target_sha256:
            log_message(f"Failed to calculate SHA256 for target file {target_file}", "WARNING")
            return True  # Assume update needed if we can't verify target
        
        # Compare SHA256 hashes
        needs_update = source_sha256 != target_sha256
        
        if needs_update:
            log_message(f"Requirements mismatch for {venv_name}: source={source_sha256[:8]}... target={target_sha256[:8]}...", "INFO")
        else:
            log_message(f"Requirements match for {venv_name}: {source_sha256[:8]}...", "DEBUG")
        
        return needs_update, source_sha256, target_sha256
        
    except Exception as e:
        log_message(f"Error checking if {venv_name} needs update: {e}", "ERROR")
        return True, None, None  # Assume update needed on error

def get_existing_venv_paths():
    """
    Get all virtual environment paths that exist and should be backed up.
    Returns:
        list: List of existing venv paths to backup
    """
    venvs_config = get_venvs_config()
    existing_paths = []
    
    for venv_name, venv_cfg in venvs_config.items():
        venv_path = venv_cfg["path"]
        if os.path.exists(venv_path):
            existing_paths.append(venv_path)
            log_message(f"Found venv path for backup: {venv_path}")
        else:
            log_message(f"Venv path not found (skipping): {venv_path}", "DEBUG")
    
    return existing_paths

def update_venv(venv_name, venv_cfg):
    """
    Update a virtual environment by copying the source requirements file and running pip install.
    
    Returns:
        Tuple[bool, bool]: (success, packages_updated)
    """
    try:
        venv_path = venv_cfg["path"]
        requirements_source = venv_cfg.get("requirements_source")
        
        if not requirements_source:
            log_message(f"No requirements source for {venv_name}, skipping", "WARNING")
            return True, False
        
        # Get source and target paths
        source_file = get_requirements_file_path(venv_name)
        target_file = get_target_requirements_path(venv_path)
        
        if not source_file.exists():
            log_message(f"Source requirements file {source_file} not found for {venv_name}", "ERROR")
            return False, False
        
        # Ensure target directory exists
        target_dir = os.path.dirname(target_file)
        os.makedirs(target_dir, exist_ok=True)
        
        # Copy source requirements file to target location
        log_message(f"Copying {source_file} to {target_file}")
        shutil.copy2(source_file, target_file)
        
        # Verify the copy was successful
        if not os.path.exists(target_file):
            log_message(f"Failed to copy requirements file to {target_file}", "ERROR")
            return False, False
        
        # Run pip install to update the virtual environment
        log_message(f"Running pip install for {venv_name}...")
        pip_path = os.path.join(venv_path, "bin", "pip")
        
        # First upgrade pip if configured
        if venv_cfg.get("upgrade_pip", False):
            log_message(f"Upgrading pip for {venv_name}")
            subprocess.run([pip_path, "install", "--upgrade", "pip"], check=True, timeout=300)
        
        # Install/upgrade packages from requirements
        result = subprocess.run([
            pip_path, "install", "-r", target_file, "--upgrade"
        ], capture_output=True, text=True, timeout=300)
        
        if result.returncode != 0:
            log_message(f"pip install failed for {venv_name}: {result.stderr}", "ERROR")
            return False, False
        
        log_message(f"Successfully updated {venv_name} virtual environment")
        return True, True
        
    except Exception as e:
        log_message(f"Failed to update {venv_name}: {e}", "ERROR")
        return False, False

def verify_venv(venv_name, venv_cfg):
    """
    Verify that a virtual environment is properly configured.
    Args:
        venv_name: Name of the virtual environment
        venv_cfg: Configuration dictionary for the venv
    Returns:
        dict: Verification results
    """
    verification_results = {
        "venv_exists": False,
        "activation_script_exists": False,
        "pip_available": False,
        "packages_verified": False,
        "path": venv_cfg["path"],
        "package_count": 0,
        "errors": []
    }
    
    venv_path = venv_cfg["path"]
    verification_config = get_verification_config()
    
    try:
        # Check if venv directory exists
        if os.path.exists(venv_path) and os.path.isdir(venv_path):
            verification_results["venv_exists"] = True
            
            # Check activation script
            if verification_config["check_activation_script"]:
                activate_script = os.path.join(venv_path, "bin", "activate")
                if os.path.isfile(activate_script):
                    verification_results["activation_script_exists"] = True
                else:
                    verification_results["errors"].append("Activation script missing")
            
            # Check pip availability
            pip_cmd = f". '{os.path.join(venv_path, 'bin', 'activate')}'; pip --version; deactivate"
            result = subprocess.run(["bash", "-c", pip_cmd], capture_output=True, text=True)
            if result.returncode == 0:
                verification_results["pip_available"] = True
            else:
                verification_results["errors"].append("Pip not available")
            
            # Verify packages if requested
            if verification_config["verify_packages"] and verification_results["pip_available"]:
                list_cmd = f". '{os.path.join(venv_path, 'bin', 'activate')}'; pip list --format=freeze; deactivate"
                result = subprocess.run(["bash", "-c", list_cmd], capture_output=True, text=True)
                if result.returncode == 0:
                    installed_packages = result.stdout.strip().split('\n')
                    verification_results["package_count"] = len([p for p in installed_packages if p.strip()])
                    verification_results["packages_verified"] = True
                else:
                    verification_results["errors"].append("Could not list packages")
        else:
            verification_results["errors"].append("Virtual environment directory does not exist")
    
    except Exception as e:
        verification_results["errors"].append(f"Verification error: {e}")
    
    return verification_results

def verify_all_venvs():
    """
    Verify all configured virtual environments.
    Returns:
        dict: Verification results for all venvs
    """
    venvs_config = get_venvs_config()
    verification_results = {}
    
    for venv_name, venv_cfg in venvs_config.items():
        log_message(f"Verifying virtual environment: {venv_name}")
        verification_results[venv_name] = verify_venv(venv_name, venv_cfg)
        
        # Log verification status
        result = verification_results[venv_name]
        status = "✓" if result["venv_exists"] and result["activation_script_exists"] else "✗"
        log_message(f"  Status: {status}")
        
        if result["errors"]:
            for error in result["errors"]:
                log_message(f"  Error: {error}", "WARNING")
        
        if result["packages_verified"]:
            log_message(f"  Packages: {result['package_count']} installed")
    
    return verification_results

def main(args=None):
    """
    Main entry point for venvs update module.
    Args:
        args: List of arguments (supports '--check', '--verify', '--config')
    Returns:
        dict: Status and results of the update
    """
    if args is None:
        args = []
    
    # Module directory for reference
    module_dir = Path(__file__).parent
    
    SERVICE_NAME = MODULE_CONFIG.get("metadata", {}).get("module_name", "venvs")
    venvs_config = get_venvs_config()

    # --config mode: show current configuration
    if len(args) > 0 and args[0] == "--config":
        log_message("Current venvs module configuration:")
        log_message(f"  Module: {SERVICE_NAME}")
        log_message(f"  Virtual environments: {len(venvs_config)}")
        
        for venv_name, venv_cfg in venvs_config.items():
            log_message(f"    {venv_name}: {venv_cfg['path']}")
            requirements_source = venv_cfg.get('requirements_source', 'N/A')
            log_message(f"      Requirements source: {requirements_source}")
            log_message(f"      Description: {venv_cfg.get('description', 'N/A')}")
        
        return {
            "success": True,
            "config": MODULE_CONFIG,
            "venv_count": len(venvs_config),
            "venvs": list(venvs_config.keys())
        }

    # --verify mode: comprehensive verification
    if len(args) > 0 and args[0] == "--verify":
        log_message("Running comprehensive venvs verification...")
        verification = verify_all_venvs()
        
        # Check if all venvs are healthy
        all_healthy = all(
            result["venv_exists"] and result["activation_script_exists"] and not result["errors"]
            for result in verification.values()
        )
        
        return {
            "success": all_healthy,
            "verification_summary": {
                "total_venvs": len(verification),
                "healthy_venvs": sum(1 for v in verification.values() if v.get('venv_exists') and v.get('pip_available')),
                "package_counts": {name: v.get('package_count', 0) for name, v in verification.items()}
            },
            "venv_count": len(verification)
        }

    # --check mode: simple existence check
    if len(args) > 0 and args[0] == "--check":
        log_message("Checking virtual environments...")
        existing_count = 0
        missing_venvs = []
        sha256_status = {}
        
        for venv_name, venv_cfg in venvs_config.items():
            if os.path.exists(venv_cfg["path"]):
                existing_count += 1
                log_message(f"✓ {venv_name}: {venv_cfg['path']}")
                
                # Check SHA256 status for existing venvs
                needs_update, source_sha256, target_sha256 = check_venv_needs_update(venv_name, venv_cfg)
                sha256_status[venv_name] = {
                    "needs_update": needs_update,
                    "source_sha256": source_sha256[:8] + "..." if source_sha256 else None,
                    "target_sha256": target_sha256[:8] + "..." if target_sha256 else None
                }
                
                if needs_update:
                    log_message(f"  → Requirements mismatch detected, update needed")
                else:
                    log_message(f"  → Requirements match, up to date")
            else:
                missing_venvs.append(venv_name)
                log_message(f"✗ {venv_name}: {venv_cfg['path']} (missing)")
        
        log_message(f"Found {existing_count}/{len(venvs_config)} virtual environments")
        
        return {
            "success": len(missing_venvs) == 0,
            "existing_count": existing_count,
            "total_count": len(venvs_config),
            "missing_venvs": missing_venvs,
            "sha256_status": sha256_status
        }

    # Main update process
    if not venvs_config:
        log_message("No virtual environments configured", "WARNING")
        return {"success": True, "updated": False, "message": "No venvs configured"}

    log_message(f"Starting virtual environment updates for {len(venvs_config)} environments...")
    
    # Initialize StateManager for backups
    state_manager = StateManager("/var/backups/venvs")

    # Check if any updates are actually needed first
    venvs_needing_updates = []
    venv_sha256_info = {}
    
    for venv_name, venv_cfg in venvs_config.items():
        log_message(f"Checking {venv_name} for updates...")
        
        needs_update, source_sha256, target_sha256 = check_venv_needs_update(venv_name, venv_cfg)
        
        if needs_update:
            venvs_needing_updates.append(venv_name)
            venv_sha256_info[venv_name] = {
                "source_sha256": source_sha256,
                "target_sha256": target_sha256,
                "needs_update": True
            }
            log_message(f"✓ {venv_name} needs update", "INFO")
        else:
            venv_sha256_info[venv_name] = {
                "source_sha256": source_sha256,
                "target_sha256": target_sha256,
                "needs_update": False
            }
            log_message(f"✓ {venv_name} is up to date", "DEBUG")

    # If no updates needed, skip backup and return early
    if not venvs_needing_updates:
        log_message("All virtual environments are already up to date")
        
        # Run verification to confirm
        log_message("Running verification...")
        verification = verify_all_venvs()
        
        # Return concise summary instead of massive data dump
        return {
            "success": True, 
            "updated": False, 
            "message": "All virtual environments already up to date",
            "verification_summary": {
                "total_venvs": len(verification),
                "healthy_venvs": sum(1 for v in verification.values() if v.get('venv_exists') and v.get('pip_available')),
                "package_counts": {name: v.get('package_count', 0) for name, v in verification.items()}
            },
            "sha256_status": venv_sha256_info,
            "backup_created": False,
            "venv_count": len(venvs_config)
        }

    log_message(f"Found {len(venvs_needing_updates)} virtual environments needing updates: {', '.join(venvs_needing_updates)}")

    # Create backup only for venvs that need updates
    backup_success = None
    if venvs_needing_updates:
        # Get paths for venvs that need updates
        files_to_backup = []
        for venv_name in venvs_needing_updates:
            venv_cfg = venvs_config[venv_name]
            venv_path = venv_cfg["path"]
            if os.path.exists(venv_path):
                files_to_backup.append(venv_path)
                log_message(f"Found venv path for backup: {venv_path}")
        
        if files_to_backup:
            log_message(f"Creating backup for {len(files_to_backup)} virtual environments that need updates...")
            
            # Create comprehensive backup using StateManager
            backup_success = state_manager.backup_module_state(
                module_name=SERVICE_NAME,
                description="pre_venv_updates",
                files=files_to_backup
            )
            
            if not backup_success:
                log_message("Failed to create backup", "ERROR")
                return {"success": False, "error": "Backup failed"}
            
            log_message("Backup created successfully")
        else:
            log_message("No existing virtual environments found for backup (all are new)", "INFO")
            backup_success = True  # No backup needed for new venvs

    # Update only the virtual environments that need updating
    results = {}
    failed_venvs = []
    actually_updated = []
    
    try:
        # Only process venvs that actually need updates
        for venv_name in venvs_needing_updates:
            venv_cfg = venvs_config[venv_name]
            log_message(f"Processing {venv_name}...")
            
            success, packages_updated = update_venv(venv_name, venv_cfg)
            results[venv_name] = success
            
            if not success:
                failed_venvs.append(venv_name)
            elif packages_updated:  # Only count as actually updated if packages were installed/upgraded
                actually_updated.append(venv_name)
            
            log_message("----------------------------------------")
        
        # Check if any updates failed
        if failed_venvs:
            raise Exception(f"Failed to update {len(failed_venvs)} virtual environments: {', '.join(failed_venvs)}")
        
        if actually_updated:
            log_message(f"Successfully updated {len(actually_updated)} virtual environments: {', '.join(actually_updated)}")
        else:
            log_message("All virtual environments were already up to date")
        
        # Run post-update verification
        log_message("Running post-update verification...")
        verification = verify_all_venvs()
        
        # Note: Backup cleanup is handled automatically by StateManager
        cleaned_count = 0
        
        return {
            "success": True, 
            "updated": len(actually_updated) > 0, 
            "results": results,
            "actually_updated": actually_updated,
            "verification_summary": {
                "total_venvs": len(verification),
                "healthy_venvs": sum(1 for v in verification.values() if v.get('venv_exists') and v.get('pip_available')),
                "package_counts": {name: v.get('package_count', 0) for name, v in verification.items()}
            },
            "backup_created": backup_success,
            "backups_cleaned": cleaned_count,
            "venv_count": len(venvs_config)
        }
        
    except Exception as e:
        log_message(f"Virtual environment updates failed: {e}", "ERROR")
        
        if backup_success:
            log_message("Restoring from backup...")
            restore_success = state_manager.restore_module_state(SERVICE_NAME)
            
            if restore_success:
                log_message("Successfully restored from backup")
            else:
                log_message("Failed to restore from backup", "ERROR")
        else:
            restore_success = None
        
        return {
            "success": False, 
            "error": str(e),
            "results": results,
            "failed_venvs": failed_venvs,
            "restore_success": restore_success,
            "backup_created": backup_success
        }

if __name__ == "__main__":
    main()
