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
                "module_name": "os"
            },
            "config": {
                "package_manager": {
                    "type": "apt",
                    "update_command": ["apt", "update"],
                    "upgrade_command": ["apt", "upgrade", "-y"],
                    "autoremove_command": ["apt", "autoremove", "-y"],
                    "clean_command": ["apt", "clean"],
                    "list_upgradable_command": ["apt", "list", "--upgradable"]
                },
                "backup": {
                    "backup_dir": "/var/backups/updates",
                    "include_paths": [
                        "/var/lib/dpkg/status",
                        "/var/lib/apt/extended_states"
                    ]
                },
                "safety": {
                    "create_snapshot": true,
                    "max_upgrade_count": 100,
                    "skip_kernel_updates": False
                }
            }
        }

# Global configuration
MODULE_CONFIG = load_module_config()

def get_backup_config():
    """Get backup configuration from module config."""
    return MODULE_CONFIG["config"]["backup"]

def get_package_manager_config():
    """Get package manager configuration from module config."""
    return MODULE_CONFIG["config"]["package_manager"]

def get_safety_config():
    """Get safety configuration from module config."""
    return MODULE_CONFIG["config"]["safety"]

def check_updates():
    """
    Check for available package updates using configured command.
    Returns:
        int: Number of upgradable packages
        str: List of upgradable packages (if any)
    """
    try:
        pm_config = get_package_manager_config()
        result = subprocess.run(
            pm_config["list_upgradable_command"], 
            capture_output=True, text=True
        )
        if result.returncode == 0:
            lines = result.stdout.strip().splitlines()
            # The first line is 'Listing...'
            upgradable = lines[1:] if len(lines) > 1 else []
            return len(upgradable), "\n".join(upgradable)
        else:
            log_message(f"Failed to check for updates: {result.stderr}", "ERROR")
            return -1, "apt list failed"
    except Exception as e:
        log_message(f"Error during update check: {e}", "ERROR")
        return -1, str(e)

def run_package_command(command_name, command):
    """
    Run a package manager command with proper logging.
    Args:
        command_name: Human-readable name for the command
        command: List of command arguments
    Returns:
        bool: True if successful, False otherwise
    """
    log_message(command_name)
    try:
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            log_message(f"{command_name} failed: {result.stderr}", "ERROR")
            return False
        else:
            if result.stdout.strip():
                log_message(result.stdout)
            return True
    except Exception as e:
        log_message(f"{command_name} error: {e}", "ERROR")
        return False

def run_os_update():
    """
    Run OS update sequence using configured commands.
    Returns:
        bool: True if successful, False otherwise
    """
    pm_config = get_package_manager_config()
    
    steps = [
        ("Updating package lists", pm_config["update_command"]),
        ("Upgrading packages", pm_config["upgrade_command"]),
        ("Autoremoving unused packages", pm_config["autoremove_command"]),
        ("Cleaning up", pm_config["clean_command"])
    ]
    
    for desc, cmd in steps:
        if not run_package_command(desc, cmd):
            return False
    
    return True

def verify_os_update():
    """
    Verify that the OS update completed successfully.
    Returns:
        dict: Verification results with status and details
    """
    verification_results = {
        "package_manager_available": False,
        "no_broken_packages": False,
        "upgradable_count": 0,
        "details": ""
    }
    
    try:
        pm_config = get_package_manager_config()
        
        # Check if package manager is available
        result = subprocess.run([pm_config["type"], "--version"], capture_output=True, text=True)
        verification_results["package_manager_available"] = (result.returncode == 0)
        
        # Check for broken packages
        result = subprocess.run(["dpkg", "--audit"], capture_output=True, text=True)
        verification_results["no_broken_packages"] = (result.returncode == 0 and not result.stdout.strip())
        
        # Check remaining upgradable packages
        count, details = check_updates()
        verification_results["upgradable_count"] = count if count >= 0 else 0
        verification_results["details"] = details
        
        # Log verification results
        for check, result in verification_results.items():
            if check not in ["upgradable_count", "details"]:
                status = "✓" if result else "✗"
                log_message(f"OS verification - {check}: {status}")
        
        log_message(f"OS verification - remaining upgradable packages: {verification_results['upgradable_count']}")
        
    except Exception as e:
        log_message(f"Error during OS verification: {e}", "ERROR")
    
    return verification_results

def main(args=None):
    """
    Main entry point for OS update module.
    Args:
        args: List of arguments (supports '--check', '--verify', '--config')
    Returns:
        dict: Status and results of the update
    """
    if args is None:
        args = []
    
    SERVICE_NAME = MODULE_CONFIG["metadata"]["module_name"]
    pm_config = get_package_manager_config()
    safety_config = get_safety_config()

    # --config mode: show current configuration
    if len(args) > 0 and args[0] == "--config":
        log_message("Current OS module configuration:")
        log_message(f"  Package manager: {pm_config['type']}")
        log_message(f"  Update command: {' '.join(pm_config['update_command'])}")
        log_message(f"  Upgrade command: {' '.join(pm_config['upgrade_command'])}")
        
        backup_config = get_backup_config()
        log_message(f"  Backup dir: {backup_config['backup_dir']}")
        log_message(f"  Backup paths: {backup_config['include_paths']}")
        
        log_message(f"  Create snapshot: {safety_config['create_snapshot']}")
        log_message(f"  Max upgrade count: {safety_config['max_upgrade_count']}")
        
        return {
            "success": True,
            "config": MODULE_CONFIG
        }

    # --verify mode: comprehensive system verification
    if len(args) > 0 and args[0] == "--verify":
        log_message("Running comprehensive OS verification...")
        verification = verify_os_update()
        
        all_checks_passed = all([
            verification["package_manager_available"],
            verification["no_broken_packages"]
        ])
        
        return {
            "success": all_checks_passed,
            "verification": verification,
            "config": MODULE_CONFIG
        }

    # --check mode: simple update check
    if len(args) > 0 and args[0] == "--check":
        count, upgradable = check_updates()
        if count > 0:
            log_message(f"{count} package(s) can be upgraded:\n{upgradable}")
            return {"success": True, "upgradable": count, "details": upgradable}
        elif count == 0:
            log_message("No packages to upgrade.")
            return {"success": True, "upgradable": 0}
        else:
            log_message("Failed to check for updates.", "ERROR")
            return {"success": False, "error": upgradable}

    # Check if updates are available
    count, upgradable = check_updates()
    if count < 0:
        log_message("Failed to check for updates", "ERROR")
        return {"success": False, "error": "Update check failed"}
    
    if count == 0:
        log_message("No packages to upgrade")
        verification = verify_os_update()
        return {
            "success": True, 
            "updated": False, 
            "upgradable": 0,
            "verification": verification,
            "config": MODULE_CONFIG
        }

    # Check safety limits
    if count > safety_config["max_upgrade_count"]:
        log_message(f"Too many packages to upgrade ({count} > {safety_config['max_upgrade_count']}). Aborting for safety.", "ERROR")
        return {"success": False, "error": f"Too many packages ({count})"}

    log_message(f"Starting OS update for {count} packages...")
    
    # Create backup if configured
    rollback_point = None
    if safety_config["create_snapshot"]:
        log_message("Creating system snapshot...")
        
        backup_config = get_backup_config()
        state_manager = StateManager(backup_config["backup_dir"])
        
        # Get files to backup from configuration
        files_to_backup = []
        for path in backup_config["include_paths"]:
            if os.path.exists(path):
                files_to_backup.append(path)
                log_message(f"Found OS file for backup: {path}")
            else:
                log_message(f"OS file not found (skipping): {path}", "DEBUG")
        
        if files_to_backup:
            log_message(f"Creating backup for {len(files_to_backup)} OS files...")
            
            rollback_point = rollback.create_rollback_point(
                module_name=SERVICE_NAME,
                description=f"pre_update_{count}_packages",
                files=files_to_backup
            )
            
            if rollback_point:
                log_message(f"Rollback point created with {len(rollback_point)} backups")
            else:
                log_message("Failed to create rollback point", "WARNING")

    # Perform the update
    log_message("Running OS update sequence...")
    try:
        if not run_os_update():
            raise Exception("OS update sequence failed")
        
        # Verify the update
        log_message("Verifying OS update...")
        verification = verify_os_update()
        
        # Check if update was successful
        new_count, _ = check_updates()
        if new_count >= 0 and new_count < count:
            log_message(f"Successfully updated OS packages. Remaining upgradable: {new_count}")
            
            return {
                "success": True, 
                "updated": True, 
                "packages_upgraded": count - new_count,
                "remaining_upgradable": new_count,
                "verification": verification,
                "rollback_point": rollback_point,
                "config": MODULE_CONFIG
            }
        else:
            raise Exception("Update verification failed - package count did not decrease as expected")
            
    except Exception as e:
        log_message(f"OS update failed: {e}", "ERROR")
        
        # Restore from rollback point if available
        if rollback_point:
            log_message("Restoring from rollback point...")
            rollback_success = rollback.restore_rollback_point(rollback_point)
            
            if rollback_success:
                log_message("Successfully restored from rollback point")
            else:
                log_message("Failed to restore from rollback point", "ERROR")
        else:
            rollback_success = False
        
        return {
            "success": False, 
            "error": str(e),
            "rollback_success": rollback_success,
            "rollback_point": rollback_point,
            "config": MODULE_CONFIG
        }

if __name__ == "__main__":
    main()
