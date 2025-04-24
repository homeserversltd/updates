import os
import subprocess
import sys
from initialization.files.user_local_lib.updates import log_message

def check_atuin_version():
    """
    Check the current version of Atuin if installed.
    
    Returns:
        str: Version string or None if not installed
    """
    try:
        result = subprocess.run(
            ["atuin", "--version"],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode == 0:
            # Extract version from output (typically "atuin x.y.z")
            version_parts = result.stdout.strip().split()
            if len(version_parts) >= 2:
                return version_parts[1]
        return None
    except FileNotFoundError:
        return None

def install_atuin():
    """
    Install Atuin if not already installed.
    
    Returns:
        bool: True if installation was successful, False otherwise
    """
    log_message("Installing Atuin...", "INFO")
    try:
        # Using the official installation method
        result = subprocess.run(
            ["bash", "-c", "curl --proto '=https' --tlsv1.2 -sSf https://setup.atuin.sh | sh"],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode == 0:
            log_message("Atuin installation successful", "INFO")
            return True
        else:
            log_message(f"Atuin installation failed: {result.stderr}", "ERROR")
            return False
    except Exception as e:
        log_message(f"Error during Atuin installation: {str(e)}", "ERROR")
        return False

def configure_atuin():
    """
    Configure Atuin for the current user.
    
    Returns:
        bool: True if configuration was successful, False otherwise
    """
    log_message("Configuring Atuin...", "INFO")
    
    # Ensure config directory exists
    config_dir = os.path.expanduser("~/.config/atuin")
    os.makedirs(config_dir, exist_ok=True)
    
    # Create or update config file
    config_file = os.path.join(config_dir, "config.toml")
    with open(config_file, "w") as f:
        f.write("""
# Atuin configuration
update_check = true
dialect = "us"
key_map = "auto"

[sync]
auto_sync = true

[stats]
disable = false
""")
    
    log_message("Atuin configuration completed", "INFO")
    return True

def main(args=None):
    """
    Main entry point for Atuin update module.
    
    Args:
        args: List of arguments (unused in this module)
        
    Returns:
        dict: Status and results of the update
    """
    if args is None:
        args = []
        
    log_message("Starting Atuin update process", "INFO")
    
    results = {
        "success": False,
        "installed": False,
        "configured": False,
        "version": None,
    }
    
    # Check current version
    current_version = check_atuin_version()
    if current_version:
        log_message(f"Atuin is already installed (version {current_version})", "INFO")
        results["installed"] = True
        results["version"] = current_version
    else:
        # Install Atuin
        install_success = install_atuin()
        if install_success:
            results["installed"] = True
            # Check version after install
            new_version = check_atuin_version()
            if new_version:
                results["version"] = new_version
                log_message(f"Installed Atuin version {new_version}", "INFO")
    
    # Configure Atuin (always run to ensure proper configuration)
    config_success = configure_atuin()
    results["configured"] = config_success
    
    # Set overall success
    results["success"] = results["installed"] and results["configured"]
    
    log_message(f"Atuin update completed. Success: {results['success']}", 
                "INFO" if results["success"] else "WARNING")
    
    return results

if __name__ == "__main__":
    main()
