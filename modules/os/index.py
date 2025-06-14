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

Handles update logic specific to the operating system.
Implements a main(args) entrypoint for orchestrated updates.
"""

import os
import sys
import json
import subprocess
from typing import Dict, Any, List, Optional
from updates.utils.index import get_module_version
from updates.utils.logger import log_message
from updates.utils.config import get_module_config

__version__ = get_module_version(os.path.dirname(os.path.abspath(__file__)))

def get_package_manager_config() -> Dict[str, Any]:
    """Get package manager configuration from index.json"""
    config = get_module_config()
    return config["config"]["package_manager"]

def get_safety_config() -> Dict[str, Any]:
    """Get safety configuration from index.json"""
    config = get_module_config()
    return config["config"]["safety"]

def run_command(command: List[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a command and return the result"""
    try:
        return subprocess.run(command, check=check, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        log_message(f"Command failed: {' '.join(command)}", "ERROR")
        log_message(f"Error: {e.stderr}", "ERROR")
        raise

def check_package_manager() -> bool:
    """Check if package manager is available"""
    try:
        run_command(["which", "apt"])
        return True
    except subprocess.CalledProcessError:
        log_message("Package manager (apt) not found", "ERROR")
        return False

def count_upgradable_packages() -> int:
    """Count number of upgradable packages"""
    try:
        result = run_command(get_package_manager_config()["list_upgradable_command"])
        # Subtract 1 to exclude the header line
        return len(result.stdout.strip().split('\n')) - 1
    except subprocess.CalledProcessError:
        log_message("Failed to count upgradable packages", "ERROR")
        return 0

def verify_system_state() -> Dict[str, Any]:
    """Verify system state after updates"""
    verification = {
        "package_manager_available": check_package_manager(),
        "no_broken_packages": True,
        "remaining_upgradable": 0
    }
    
    # Check for broken packages
    try:
        result = run_command(["dpkg", "--audit"])
        verification["no_broken_packages"] = len(result.stdout.strip()) == 0
    except subprocess.CalledProcessError:
        verification["no_broken_packages"] = False
    
    # Count remaining upgradable packages
    verification["remaining_upgradable"] = count_upgradable_packages()
    
    return verification

def main(args: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Main entry point for OS updates
    
    Args:
        args: Command line arguments
        
    Returns:
        Dictionary containing update results
    """
    if args is None:
        args = []
        
    # Parse command line arguments
    if "--check" in args:
        return {
            "success": True,
            "upgradable": count_upgradable_packages()
        }
    elif "--verify" in args:
        return {
            "success": True,
            "verification": verify_system_state()
        }
    elif "--config" in args:
        return {
            "success": True,
            "config": get_module_config()
        }
    
    # Get configurations
    package_manager_config = get_package_manager_config()
    safety_config = get_safety_config()
    
    # Initialize result
    result = {
        "success": False,
        "updated": False,
        "upgradable": 0,
        "verification": {},
        "config": get_module_config()
    }
    
    try:
        # Check package manager availability
        if not check_package_manager():
            result["error"] = "Package manager not available"
            return result
            
        # Count upgradable packages
        upgradable_count = count_upgradable_packages()
        result["upgradable"] = upgradable_count
        
        # Check safety limits
        if upgradable_count > safety_config["max_upgrade_count"]:
            result["error"] = f"Too many packages to upgrade ({upgradable_count} > {safety_config['max_upgrade_count']})"
            return result
            
        # Update package lists
        log_message("Updating package lists...")
        run_command(package_manager_config["update_command"])
        
        # Upgrade packages
        log_message("Upgrading packages...")
        run_command(package_manager_config["upgrade_command"])
        
        # Remove unused packages
        log_message("Removing unused packages...")
        run_command(package_manager_config["autoremove_command"])
        
        # Clean package cache
        log_message("Cleaning package cache...")
        run_command(package_manager_config["clean_command"])
        
        # Verify system state
        result["verification"] = verify_system_state()
        
        # Set success if no broken packages and package manager is available
        result["success"] = (
            result["verification"]["package_manager_available"] and
            result["verification"]["no_broken_packages"]
        )
        result["updated"] = True
        
    except Exception as e:
        log_message(f"Update failed: {str(e)}", "ERROR")
        result["error"] = str(e)
        
    return result

if __name__ == "__main__":
    result = main(sys.argv[1:] if len(sys.argv) > 1 else [])
    print(json.dumps(result, indent=2))
