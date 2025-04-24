import os
import subprocess
import sys
import shutil
import pwd
import urllib.request
import json
from initialization.files.user_local_lib.updates import log_message

# --- Helpers for backup/restore/cleanup ---
def get_admin_user():
    """
    Get the username for UID 1000 (admin user).
    Returns:
        str: Username or None if not found
    """
    try:
        return pwd.getpwuid(1000).pw_name
    except Exception as e:
        log_message(f"Failed to get admin user: {e}", "ERROR")
        return None

def get_atuin_bin_path(admin_user):
    """
    Get the path to the Atuin binary for the given user.
    """
    return f"/home/{admin_user}/.atuin/bin/atuin"

def backup_create(service_name, bin_path, ext=".bin"):
    """
    Create a backup of the Atuin binary.
    """
    backup_path = bin_path + ext
    try:
        if os.path.exists(bin_path):
            shutil.copy2(bin_path, backup_path)
            log_message(f"Backup created at {backup_path}")
            return backup_path
        else:
            log_message(f"No binary found to backup at {bin_path}", "WARNING")
            return None
    except Exception as e:
        log_message(f"Failed to create backup: {e}", "ERROR")
        return None

def backup_restore(service_name, bin_path, ext=".bin"):
    """
    Restore the Atuin binary from backup.
    """
    backup_path = bin_path + ext
    try:
        if os.path.exists(backup_path):
            shutil.copy2(backup_path, bin_path)
            log_message(f"Restored backup from {backup_path}")
            return True
        else:
            log_message(f"No backup found at {backup_path}", "ERROR")
            return False
    except Exception as e:
        log_message(f"Failed to restore backup: {e}", "ERROR")
        return False

def backup_cleanup(service_name, bin_path, ext=".bin"):
    """
    Remove the backup file after successful update.
    """
    backup_path = bin_path + ext
    try:
        if os.path.exists(backup_path):
            os.remove(backup_path)
            log_message(f"Cleaned up backup {backup_path}")
    except Exception as e:
        log_message(f"Failed to cleanup backup: {e}", "WARNING")

# --- Atuin version helpers ---
def check_atuin_version(bin_path):
    """
    Check the current version of Atuin if installed at bin_path.
    Returns:
        str: Version string or None if not installed
    """
    try:
        if not os.path.isfile(bin_path) or not os.access(bin_path, os.X_OK):
            return None
        result = subprocess.run([bin_path, "--version"], capture_output=True, text=True, check=False)
        if result.returncode == 0:
            version_parts = result.stdout.strip().split()
            if len(version_parts) >= 2:
                return version_parts[1]
        return None
    except Exception:
        return None

def get_latest_atuin_version():
    """
    Get the latest Atuin version from GitHub releases.
    Returns:
        str: Latest version string or None
    """
    try:
        with urllib.request.urlopen("https://api.github.com/repos/atuinsh/atuin/releases/latest") as resp:
            data = json.load(resp)
            tag = data.get("tag_name", "")
            if tag.startswith("v"):
                return tag[1:]
            return tag
    except Exception as e:
        log_message(f"Failed to get latest version info: {e}", "ERROR")
        return None

def install_atuin(admin_user):
    """
    Install Atuin using the official script as the admin user.
    Returns:
        bool: True if install succeeded, False otherwise
    """
    log_message("Installing Atuin...", "INFO")
    try:
        # Use 'su - <user> -c ...' to run as admin user
        cmd = [
            "su", "-", admin_user, "-c",
            "bash <(curl --proto '=https' --tlsv1.2 -sSf https://setup.atuin.sh)"
        ]
        result = subprocess.run(
            " ".join(cmd), shell=True, capture_output=True, text=True, check=False
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

def main(args=None):
    """
    Main entry point for Atuin update module.
    Args:
        args: List of arguments (supports '--check')
    Returns:
        dict: Status and results of the update
    """
    if args is None:
        args = []
    SERVICE_NAME = "atuin"
    admin_user = get_admin_user()
    if not admin_user:
        log_message("Could not determine admin user (UID 1000)", "ERROR")
        return {"success": False, "error": "No admin user"}
    ATUIN_BIN = get_atuin_bin_path(admin_user)

    # --check mode
    if len(args) > 0 and args[0] == "--check":
        version = check_atuin_version(ATUIN_BIN)
        if version:
            log_message(f"OK - Current version: {version}")
            return {"success": True, "version": version}
        else:
            log_message(f"Atuin binary not found at {ATUIN_BIN}", "ERROR")
            return {"success": False, "error": "Not found"}

    # Get current version
    current_version = check_atuin_version(ATUIN_BIN)
    if not current_version:
        log_message("Failed to get current version of Atuin", "ERROR")
        return {"success": False, "error": "No current version"}
    log_message(f"Current Atuin version: {current_version}")

    # Get latest version
    latest_version = get_latest_atuin_version()
    if not latest_version:
        log_message("Failed to get latest version information", "ERROR")
        return {"success": False, "error": "No latest version"}
    log_message(f"Latest available version: {latest_version}")

    # Compare and update if needed
    if current_version != latest_version:
        log_message("Update available. Creating backup...")
        backup_create(SERVICE_NAME, ATUIN_BIN)
        log_message("Installing update...")
        if not install_atuin(admin_user):
            log_message("Failed to update Atuin", "ERROR")
            log_message("Restoring from backup...")
            backup_restore(SERVICE_NAME, ATUIN_BIN)
            return {"success": False, "error": "Update failed, restored backup"}
        # Verify new version
        new_version = check_atuin_version(ATUIN_BIN)
        if new_version == latest_version:
            log_message(f"Successfully updated Atuin from {current_version} to {latest_version}")
            backup_cleanup(SERVICE_NAME, ATUIN_BIN)
            return {"success": True, "updated": True, "old_version": current_version, "new_version": new_version}
        else:
            log_message(f"Version mismatch after update. Expected: {latest_version}, Got: {new_version}", "ERROR")
            log_message("Restoring from backup...")
            backup_restore(SERVICE_NAME, ATUIN_BIN)
            return {"success": False, "error": "Version mismatch after update, restored backup"}
    else:
        log_message(f"Atuin is already at the latest version ({current_version})")
        return {"success": True, "updated": False, "version": current_version}

if __name__ == "__main__":
    main()
