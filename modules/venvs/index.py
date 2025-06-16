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

def load_requirements_from_source(requirements_source):
    """
    Load requirements from a source file in the src/ directory.
    Args:
        requirements_source: Filename of requirements file in src/
    Returns:
        list: List of package requirements, or empty list if file not found
    """
    try:
        module_dir = os.path.dirname(__file__)
        src_dir = os.path.join(module_dir, "src")
        requirements_path = os.path.join(src_dir, requirements_source)
        
        if not os.path.exists(requirements_path):
            log_message(f"Requirements file not found: {requirements_path}", "WARNING")
            return []
        
        with open(requirements_path, 'r') as f:
            requirements = []
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    requirements.append(line)
            
        log_message(f"Loaded {len(requirements)} requirements from {requirements_source}")
        return requirements
        
    except Exception as e:
        log_message(f"Failed to load requirements from {requirements_source}: {e}", "ERROR")
        return []

def parse_requirement(requirement_line):
    """
    Parse a requirement line to extract package name and version.
    Args:
        requirement_line: A pip requirement line (e.g., "Flask==3.1.0" or "requests>=2.28.0")
    Returns:
        tuple: (package_name, version_spec, operator) or (None, None, None) if parsing fails
    """
    import re
    
    # Handle different version operators
    version_pattern = r'^([a-zA-Z0-9_-]+)\s*([><=!~]+)\s*([0-9.]+.*?)(?:\s*;.*)?$'
    match = re.match(version_pattern, requirement_line.strip())
    
    if match:
        package_name = match.group(1).lower()
        operator = match.group(2)
        version = match.group(3)
        return package_name, version, operator
    
    # Handle package names without version specs
    simple_pattern = r'^([a-zA-Z0-9_-]+)(?:\s*;.*)?$'
    match = re.match(simple_pattern, requirement_line.strip())
    if match:
        package_name = match.group(1).lower()
        return package_name, None, None
    
    return None, None, None

def check_packages_match_requirements(venv_path, requirements):
    """
    Check if installed packages match the requirements exactly.
    Args:
        venv_path: Path to the virtual environment
        requirements: List of requirement strings
    Returns:
        tuple: (all_match, missing_packages, version_mismatches, installed_packages)
    """
    try:
        # Get currently installed packages
        activate_script = os.path.join(venv_path, "bin", "activate")
        list_cmd = f". '{activate_script}'; pip list --format=freeze; deactivate"
        result = subprocess.run(["bash", "-c", list_cmd], capture_output=True, text=True)
        
        if result.returncode != 0:
            log_message(f"Failed to list packages: {result.stderr}", "DEBUG")
            return False, [], [], {}
        
        # Parse installed packages
        installed_packages = {}
        for line in result.stdout.strip().split('\n'):
            if line.strip() and '==' in line:
                parts = line.strip().split('==')
                if len(parts) == 2:
                    pkg_name = parts[0].lower()
                    version = parts[1]
                    installed_packages[pkg_name] = version
        
        # Parse requirements and check matches
        missing_packages = []
        version_mismatches = []
        
        for req in requirements:
            pkg_name, req_version, operator = parse_requirement(req)
            
            if pkg_name is None:
                log_message(f"Could not parse requirement: {req}", "DEBUG")
                continue
            
            if pkg_name not in installed_packages:
                missing_packages.append(req)
                continue
            
            installed_version = installed_packages[pkg_name]
            
            # For exact version requirements (==), check exact match
            if operator == "==" and req_version:
                if installed_version != req_version:
                    version_mismatches.append(f"{pkg_name}: installed {installed_version}, required {req_version}")
            # For other operators or no version spec, assume it's acceptable
            # (more complex version comparison would require packaging library)
        
        all_match = len(missing_packages) == 0 and len(version_mismatches) == 0
        
        return all_match, missing_packages, version_mismatches, installed_packages
        
    except Exception as e:
        log_message(f"Error checking package requirements: {e}", "DEBUG")
        return False, [], [], {}

def update_venv(venv_name, venv_cfg):
    """
    Update a single virtual environment with packages from source requirements file.
    Only performs updates if packages don't match requirements.
    Args:
        venv_name: Name of the virtual environment
        venv_cfg: Configuration dictionary for the venv
    Returns:
        bool: True if update succeeded, False otherwise
    """
    venv_path = venv_cfg["path"]
    requirements_source = venv_cfg.get("requirements_source")
    upgrade_pip = venv_cfg.get("upgrade_pip", False)
    system_packages = venv_cfg.get("system_packages", False)
    description = venv_cfg.get("description", "")

    log_message(f"Checking virtual environment: {venv_name}")
    if description:
        log_message(f"  Description: {description}")
    log_message(f"  Path: {venv_path}")
    log_message(f"  Requirements source: {requirements_source}")

    # Load packages from source file
    if requirements_source:
        packages = load_requirements_from_source(requirements_source)
        if not packages:
            log_message(f"No packages loaded from {requirements_source}", "WARNING")
    else:
        packages = []
        log_message("No requirements source specified", "WARNING")

    # Create venv if missing
    venv_created = False
    if not os.path.isdir(venv_path):
        log_message(f"Creating virtual environment at {venv_path}")
        
        # Build venv creation command
        venv_cmd = ["python3", "-m", "venv"]
        if system_packages:
            venv_cmd.append("--system-site-packages")
        venv_cmd.append(venv_path)
        
        result = subprocess.run(venv_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            log_message(f"Failed to create venv: {result.stderr}", "ERROR")
            return False
        log_message(f"Created virtual environment at {venv_path}")
        venv_created = True

    # Verify activation script exists
    activate_script = os.path.join(venv_path, "bin", "activate")
    if not os.path.isfile(activate_script):
        log_message(f"Activation script not found at {activate_script}", "ERROR")
        return False

    # Check if packages already match requirements (skip if venv was just created)
    needs_update = venv_created
    pip_needs_upgrade = False
    
    if not venv_created and packages:
        all_match, missing_packages, version_mismatches, installed_packages = check_packages_match_requirements(venv_path, packages)
        
        if all_match:
            log_message(f"  All {len(packages)} packages already match requirements")
            
            # Still check if pip needs upgrade
            if upgrade_pip:
                pip_cmd = f". '{activate_script}'; pip --version; deactivate"
                result = subprocess.run(["bash", "-c", pip_cmd], capture_output=True, text=True)
                if result.returncode == 0:
                    # Simple check - if we can run pip, assume it's fine unless explicitly requested
                    log_message(f"  Pip is available, skipping upgrade check")
                else:
                    pip_needs_upgrade = True
            
            if not pip_needs_upgrade:
                log_message(f"  No updates needed for {venv_name}")
                return True
        else:
            needs_update = True
            if missing_packages:
                log_message(f"  Missing packages: {len(missing_packages)}")
                for pkg in missing_packages[:3]:  # Show first 3
                    log_message(f"    - {pkg}")
                if len(missing_packages) > 3:
                    log_message(f"    ... and {len(missing_packages) - 3} more")
            
            if version_mismatches:
                log_message(f"  Version mismatches: {len(version_mismatches)}")
                for mismatch in version_mismatches[:3]:  # Show first 3
                    log_message(f"    - {mismatch}")
                if len(version_mismatches) > 3:
                    log_message(f"    ... and {len(version_mismatches) - 3} more")

    if not needs_update and not pip_needs_upgrade:
        return True

    # Perform updates
    log_message(f"Updating virtual environment: {venv_name}")
    
    # Build pip install command
    pip_cmd = f". '{activate_script}'; "
    
    if upgrade_pip or pip_needs_upgrade:
        log_message(f"  Upgrading pip for {venv_name}")
        pip_cmd += "pip install --upgrade pip; "
    
    if packages and needs_update:
        log_message(f"  Installing/upgrading {len(packages)} packages")
        pip_cmd += "pip install --upgrade "
        pip_cmd += " ".join(f"'{pkg}'" for pkg in packages)
        pip_cmd += "; "
    
    pip_cmd += "deactivate"

    # Run the command in a shell with timeout
    verification_config = get_verification_config()
    timeout = verification_config["timeout_seconds"]
    
    try:
        result = subprocess.run(
            ["bash", "-c", pip_cmd], 
            capture_output=True, 
            text=True, 
            timeout=timeout
        )
        if result.returncode != 0:
            log_message(f"Failed to update venv {venv_name}: {result.stderr}", "ERROR")
            return False
        
        log_message(f"Successfully updated {venv_name}")
        if result.stdout.strip():
            log_message(f"  Output: {result.stdout.strip()}", "DEBUG")
        
    except subprocess.TimeoutExpired:
        log_message(f"Timeout ({timeout}s) updating venv {venv_name}", "ERROR")
        return False
    except Exception as e:
        log_message(f"Error updating venv {venv_name}: {e}", "ERROR")
        return False

    return True

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
            "verification": verification,
            "venv_count": len(verification),
            "config": MODULE_CONFIG
        }

    # --check mode: simple existence check
    if len(args) > 0 and args[0] == "--check":
        log_message("Checking virtual environments...")
        existing_count = 0
        missing_venvs = []
        
        for venv_name, venv_cfg in venvs_config.items():
            if os.path.exists(venv_cfg["path"]):
                existing_count += 1
                log_message(f"✓ {venv_name}: {venv_cfg['path']}")
            else:
                missing_venvs.append(venv_name)
                log_message(f"✗ {venv_name}: {venv_cfg['path']} (missing)")
        
        log_message(f"Found {existing_count}/{len(venvs_config)} virtual environments")
        
        return {
            "success": len(missing_venvs) == 0,
            "existing_count": existing_count,
            "total_count": len(venvs_config),
            "missing_venvs": missing_venvs
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
    for venv_name, venv_cfg in venvs_config.items():
        venv_path = venv_cfg["path"]
        requirements_source = venv_cfg.get("requirements_source")
        
        # If venv doesn't exist, it needs creation
        if not os.path.isdir(venv_path):
            venvs_needing_updates.append(venv_name)
            continue
            
        # If no requirements, skip detailed check
        if not requirements_source:
            continue
            
        # Load and check requirements
        packages = load_requirements_from_source(requirements_source)
        if packages:
            all_match, _, _, _ = check_packages_match_requirements(venv_path, packages)
            if not all_match:
                venvs_needing_updates.append(venv_name)

    # If no updates needed, skip backup and return early
    if not venvs_needing_updates:
        log_message("All virtual environments are already up to date")
        
        # Run verification to confirm
        log_message("Running verification...")
        verification = verify_all_venvs()
        
        return {
            "success": True, 
            "updated": False, 
            "message": "All virtual environments already up to date",
            "verification": verification,
            "backup_created": False,
            "venv_count": len(venvs_config),
            "config": MODULE_CONFIG
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

    # Update all virtual environments
    results = {}
    failed_venvs = []
    actually_updated = []
    
    try:
        for venv_name, venv_cfg in venvs_config.items():
            log_message(f"Processing {venv_name}...")
            
            # Track if this venv was expected to need updates
            expected_update = venv_name in venvs_needing_updates
            
            success = update_venv(venv_name, venv_cfg)
            results[venv_name] = success
            
            if not success:
                failed_venvs.append(venv_name)
            elif expected_update:
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
            "verification": verification,
            "backup_created": backup_success,
            "backups_cleaned": cleaned_count,
            "venv_count": len(venvs_config),
            "config": MODULE_CONFIG
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
            "backup_created": backup_success,
            "config": MODULE_CONFIG
        }

if __name__ == "__main__":
    main()
