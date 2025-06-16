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

"""
OS Update Module

Operating system update management with batch processing for large package sets.
"""

import subprocess
import sys
import json
import os
from typing import Dict, Any, List, Optional

def load_module_config():
    """Load configuration from the module's index.json file."""
    try:
        config_path = os.path.join(os.path.dirname(__file__), "index.json")
        with open(config_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        log_message(f"Failed to load module config: {e}", "WARNING")
        # Return default configuration
        return {
            "metadata": {
                "schema_version": "1.0.3",
                "module_name": "os"
            },
            "config": {
                "package_manager": {
                    "update_command": ["apt", "update"],
                    "upgrade_command": ["apt", "upgrade", "-y"],
                    "autoremove_command": ["apt", "autoremove", "-y"],
                    "clean_command": ["apt", "autoclean"],
                    "list_upgradable_command": ["apt", "list", "--upgradable"]
                },
                "safety": {
                    "max_upgrade_count": 100
                }
            }
        }

# Load module configuration
MODULE_CONFIG = load_module_config()

def log_message(message: str, level: str = "INFO"):
    """Simple logging function"""
    print(f"[{level}] {message}")

def run_command(command: List[str]) -> subprocess.CompletedProcess:
    """Run a command and return the result"""
    try:
        log_message(f"Running: {' '.join(command)}")
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        if result.stdout.strip():
            log_message(f"Output: {result.stdout.strip()}")
        return result
    except subprocess.CalledProcessError as e:
        log_message(f"Command failed: {' '.join(command)}", "ERROR")
        if e.stderr:
            log_message(f"Error: {e.stderr.strip()}", "ERROR")
        raise

def get_upgradable_packages() -> List[str]:
    """Get list of upgradable package names"""
    try:
        cmd = MODULE_CONFIG["config"]["package_manager"]["list_upgradable_command"]
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        
        packages = []
        lines = result.stdout.strip().split('\n')
        
        # Skip header line and parse package names
        for line in lines[1:]:  # Skip "Listing..." header
            if line.strip() and '[upgradable' in line:
                # Extract package name (first part before /)
                package_name = line.split('/')[0].strip()
                if package_name:
                    packages.append(package_name)
        
        log_message(f"Found {len(packages)} upgradable packages")
        return packages
    except subprocess.CalledProcessError:
        log_message("Failed to get upgradable packages list", "ERROR")
        return []

def count_upgradable_packages() -> int:
    """Count number of upgradable packages"""
    return len(get_upgradable_packages())

def upgrade_packages_batch(packages: List[str]) -> bool:
    """Upgrade a specific batch of packages"""
    try:
        if not packages:
            return True
            
        log_message(f"Upgrading batch of {len(packages)} packages: {', '.join(packages[:5])}{'...' if len(packages) > 5 else ''}")
        
        # Build upgrade command with specific packages
        upgrade_cmd = MODULE_CONFIG["config"]["package_manager"]["upgrade_command"] + packages
        
        # Use DEBIAN_FRONTEND=noninteractive to prevent hanging on prompts
        env = os.environ.copy()
        env['DEBIAN_FRONTEND'] = 'noninteractive'
        
        # Don't capture output so we can see progress, add timeout to prevent infinite hanging
        log_message(f"Running: {' '.join(upgrade_cmd)}")
        result = subprocess.run(
            upgrade_cmd, 
            check=True, 
            env=env,
            timeout=1800  # 30 minute timeout for batch upgrades
        )
        
        log_message(f"Successfully upgraded {len(packages)} packages")
        return True
        
    except subprocess.TimeoutExpired:
        log_message(f"Batch upgrade timed out after 30 minutes", "ERROR")
        return False
    except subprocess.CalledProcessError as e:
        log_message(f"Failed to upgrade batch: {e}", "ERROR")
        return False

def repair_package_system() -> bool:
    """Detect and repair common package system issues"""
    try:
        log_message("Checking package system health...")
        
        # Check for interrupted dpkg operations
        try:
            result = subprocess.run(
                ["dpkg", "--audit"], 
                check=True, 
                capture_output=True, 
                text=True
            )
            if result.stdout.strip():
                log_message("Found interrupted dpkg operations, attempting repair...")
                log_message("Running: dpkg --configure -a")
                subprocess.run(["dpkg", "--configure", "-a"], check=True)
                log_message("Successfully repaired interrupted dpkg operations")
        except subprocess.CalledProcessError:
            log_message("dpkg --configure -a failed, continuing anyway", "WARNING")
        
        # Check for broken packages
        try:
            result = subprocess.run(
                ["apt", "check"], 
                check=True, 
                capture_output=True, 
                text=True
            )
        except subprocess.CalledProcessError as e:
            if "broken packages" in str(e.stderr).lower():
                log_message("Found broken packages, attempting repair...")
                log_message("Running: apt --fix-broken install")
                try:
                    env = os.environ.copy()
                    env['DEBIAN_FRONTEND'] = 'noninteractive'
                    subprocess.run(
                        ["apt", "--fix-broken", "install", "-y"], 
                        check=True, 
                        env=env
                    )
                    log_message("Successfully repaired broken packages")
                except subprocess.CalledProcessError:
                    log_message("Failed to repair broken packages", "ERROR")
                    return False
        
        # Check for held packages that might cause issues
        try:
            result = subprocess.run(
                ["apt-mark", "showhold"], 
                check=True, 
                capture_output=True, 
                text=True
            )
            if result.stdout.strip():
                held_packages = result.stdout.strip().split('\n')
                log_message(f"Found {len(held_packages)} held packages: {', '.join(held_packages)}")
        except subprocess.CalledProcessError:
            pass  # apt-mark might not be available
        
        log_message("Package system health check completed")
        return True
        
    except Exception as e:
        log_message(f"Package system repair failed: {e}", "ERROR")
        return False

def main(args: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Main entry point for OS updates with batch processing
    
    Args:
        args: Command line arguments
        
    Returns:
        Dictionary containing update results
    """
    if args is None:
        args = []
        
    log_message("Starting OS update...")
    
    # Parse command line arguments
    if "--check" in args:
        upgradable = count_upgradable_packages()
        return {
            "success": True,
            "upgradable": upgradable
        }
    
    # Initialize result
    result = {
        "success": False,
        "updated": False,
        "upgradable": 0,
        "batches_processed": 0,
        "total_upgraded": 0,
        "error": None,
        "repairs_performed": False
    }
    
    try:
        # Check if apt is available
        try:
            subprocess.run(["which", "apt"], check=True, capture_output=True)
        except subprocess.CalledProcessError:
            result["error"] = "apt package manager not found"
            return result
        
        # Repair package system before attempting updates
        if not repair_package_system():
            result["error"] = "Failed to repair package system"
            return result
        result["repairs_performed"] = True
        
        # Update package lists first
        log_message("Updating package lists...")
        update_cmd = MODULE_CONFIG["config"]["package_manager"]["update_command"]
        run_command(update_cmd)
        
        # Get list of upgradable packages
        upgradable_packages = get_upgradable_packages()
        upgradable_count = len(upgradable_packages)
        result["upgradable"] = upgradable_count
        
        if upgradable_count == 0:
            log_message("No packages to upgrade")
            result["success"] = True
            result["updated"] = False
            return result
        
        # Get safety threshold
        max_upgrade_count = MODULE_CONFIG["config"]["safety"]["max_upgrade_count"]
        
        # Process packages in batches if needed
        if upgradable_count > max_upgrade_count:
            log_message(f"Large number of packages ({upgradable_count}) detected. Processing in batches of {max_upgrade_count}")
            
            total_upgraded = 0
            batch_number = 0
            
            # Process packages in chunks
            for i in range(0, upgradable_count, max_upgrade_count):
                batch_number += 1
                batch_packages = upgradable_packages[i:i + max_upgrade_count]
                
                log_message(f"Processing batch {batch_number}: {len(batch_packages)} packages")
                
                if upgrade_packages_batch(batch_packages):
                    total_upgraded += len(batch_packages)
                    result["batches_processed"] += 1
                    log_message(f"Batch {batch_number} completed successfully")
                else:
                    log_message(f"Batch {batch_number} failed", "ERROR")
                    result["error"] = f"Failed to upgrade batch {batch_number}"
                    break
                
                # Update package lists between batches to get current state
                if i + max_upgrade_count < upgradable_count:
                    log_message("Updating package lists between batches...")
                    run_command(update_cmd)
                    
                    # Refresh the remaining packages list
                    remaining_packages = get_upgradable_packages()
                    if not remaining_packages:
                        log_message("All packages upgraded during batch processing")
                        break
                    
                    # Update the packages list for next iteration
                    upgradable_packages = remaining_packages
                    upgradable_count = len(remaining_packages)
            
            result["total_upgraded"] = total_upgraded
            
        else:
            # Standard upgrade for smaller package sets
            log_message(f"Upgrading {upgradable_count} packages...")
            upgrade_cmd = MODULE_CONFIG["config"]["package_manager"]["upgrade_command"]
            run_command(upgrade_cmd)
            result["total_upgraded"] = upgradable_count
            result["batches_processed"] = 1
        
        # Post-upgrade cleanup
        log_message("Removing unused packages...")
        autoremove_cmd = MODULE_CONFIG["config"]["package_manager"]["autoremove_command"]
        run_command(autoremove_cmd)
        
        log_message("Cleaning package cache...")
        clean_cmd = MODULE_CONFIG["config"]["package_manager"]["clean_command"]
        run_command(clean_cmd)
        
        # Check final state
        upgradable_after = count_upgradable_packages()
        result["upgradable_after"] = upgradable_after
        
        result["success"] = True
        result["updated"] = True
        
        if upgradable_after == 0:
            log_message("All packages upgraded successfully")
        else:
            log_message(f"Upgrade completed, {upgradable_after} packages still upgradable")
        
    except Exception as e:
        error_msg = f"OS update failed: {str(e)}"
        log_message(error_msg, "ERROR")
        result["error"] = error_msg
        
    return result

if __name__ == "__main__":
    result = main(sys.argv[1:] if len(sys.argv) > 1 else [])
    print(json.dumps(result, indent=2))
