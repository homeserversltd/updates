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

Simple operating system update management - just apt update && apt upgrade.
"""

import subprocess
import sys
import json
from typing import Dict, Any, List, Optional

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

def count_upgradable_packages() -> int:
    """Count number of upgradable packages"""
    try:
        result = run_command(["apt", "list", "--upgradable"])
        # Subtract 1 to exclude the header line
        lines = result.stdout.strip().split('\n')
        count = len(lines) - 1 if len(lines) > 1 else 0
        log_message(f"Found {count} upgradable packages")
        return count
    except subprocess.CalledProcessError:
        log_message("Failed to count upgradable packages", "ERROR")
        return 0

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
        "error": None
    }
    
    try:
        # Check if apt is available
        try:
            subprocess.run(["which", "apt"], check=True, capture_output=True)
        except subprocess.CalledProcessError:
            result["error"] = "apt package manager not found"
            return result
        
        # Count upgradable packages before update
        upgradable_before = count_upgradable_packages()
        result["upgradable"] = upgradable_before
        
        # Safety check - don't upgrade if too many packages
        if upgradable_before > 100:
            result["error"] = f"Too many packages to upgrade ({upgradable_before} > 100)"
            log_message(result["error"], "ERROR")
            return result
        
        if upgradable_before == 0:
            log_message("No packages to upgrade")
            result["success"] = True
            result["updated"] = False
            return result
        
        # Update package lists
        log_message("Updating package lists...")
        run_command(["apt", "update"])
        
        # Upgrade packages
        log_message(f"Upgrading {upgradable_before} packages...")
        run_command(["apt", "upgrade", "-y"])
        
        # Remove unused packages
        log_message("Removing unused packages...")
        run_command(["apt", "autoremove", "-y"])
        
        # Clean package cache
        log_message("Cleaning package cache...")
        run_command(["apt", "autoclean"])
        
        # Check if upgrade was successful
        upgradable_after = count_upgradable_packages()
        
        result["success"] = True
        result["updated"] = True
        result["upgradable_after"] = upgradable_after
        
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
