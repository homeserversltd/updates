import os
import subprocess
import shutil
import urllib.request
import json
import time
from initialization.files.user_local_lib.updates import log_message

SERVICE_NAME = "filebrowser"
DB_PATH = "/etc/filebrowser/filebrowser.db"
DATA_DIR = "/etc/filebrowser"
SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")
BIN_PATH = "/usr/local/bin/filebrowser"

# --- Backup/Restore/Cleanup helpers ---
def backup_create(service_name, path, ext):
    backup_path = path + ext
    try:
        if os.path.exists(path):
            shutil.copy2(path, backup_path)
            log_message(f"Backup created at {backup_path}")
            return backup_path
        else:
            log_message(f"No file found to backup at {path}", "WARNING")
            return None
    except Exception as e:
        log_message(f"Failed to create backup: {e}", "ERROR")
        return None

def backup_restore(service_name, path, ext):
    backup_path = path + ext
    try:
        if os.path.exists(backup_path):
            shutil.copy2(backup_path, path)
            log_message(f"Restored backup from {backup_path}")
            return True
        else:
            log_message(f"No backup found at {backup_path}", "ERROR")
            return False
    except Exception as e:
        log_message(f"Failed to restore backup: {e}", "ERROR")
        return False

def backup_cleanup(service_name):
    for path, ext in [(DB_PATH, ".db"), (SETTINGS_PATH, ".json")]:
        backup_path = path + ext
        try:
            if os.path.exists(backup_path):
                os.remove(backup_path)
                log_message(f"Cleaned up backup {backup_path}")
        except Exception as e:
            log_message(f"Failed to cleanup backup: {e}", "WARNING")

# --- Service management ---
def systemctl(action, service):
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
    try:
        result = subprocess.run(["systemctl", "is-active", "--quiet", service])
        return result.returncode == 0
    except Exception:
        return False

# --- Version helpers ---
def get_current_version():
    try:
        if not os.path.isfile(BIN_PATH) or not os.access(BIN_PATH, os.X_OK):
            return None
        # Try: filebrowser --version
        result = subprocess.run([BIN_PATH, "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            # Output: 'File Browser v2.23.0' or similar
            for line in result.stdout.splitlines():
                if "v" in line:
                    parts = line.strip().split()
                    for part in parts:
                        if part.startswith("v") and part[1:].replace(".", "").isdigit():
                            return part[1:]
            # Fallback: third word
            parts = result.stdout.strip().split()
            if len(parts) >= 3:
                return parts[2].lstrip("v")
        return None
    except Exception:
        return None

def get_latest_version():
    try:
        with urllib.request.urlopen("https://api.github.com/repos/filebrowser/filebrowser/releases/latest") as resp:
            data = json.load(resp)
            tag = data.get("tag_name", "")
            if tag.startswith("v"):
                return tag[1:]
            return tag
    except Exception as e:
        log_message(f"Failed to get latest version info: {e}", "ERROR")
        return None

# --- Update logic ---
def update_filebrowser():
    log_message("Updating Filebrowser...")
    try:
        result = subprocess.run(
            "curl -fsSL https://raw.githubusercontent.com/filebrowser/get/master/get.sh | bash",
            shell=True, capture_output=True, text=True
        )
        if result.returncode == 0:
            log_message("Filebrowser update script ran successfully.")
            return True
        else:
            log_message(f"Update failed: {result.stderr}", "ERROR")
            return False
    except Exception as e:
        log_message(f"Error during update: {e}", "ERROR")
        return False

def main(args=None):
    """
    Main entry point for Filebrowser update module.
    Args:
        args: List of arguments (supports '--check')
    Returns:
        dict: Status and results of the update
    """
    if args is None:
        args = []

    # --check mode
    if len(args) > 0 and args[0] == "--check":
        version = get_current_version()
        if version:
            log_message(f"OK - Current version: {version}")
            return {"success": True, "version": version}
        else:
            log_message(f"Filebrowser not found at {BIN_PATH} or not executable", "ERROR")
            return {"success": False, "error": "Not found"}

    # Get current and latest version
    current_version = get_current_version()
    if not current_version:
        log_message("Failed to get current version of Filebrowser", "ERROR")
        return {"success": False, "error": "No current version"}
    log_message(f"Current Filebrowser version: {current_version}")

    latest_version = get_latest_version()
    if not latest_version:
        log_message("Failed to get latest version information", "ERROR")
        return {"success": False, "error": "No latest version"}
    log_message(f"Latest available version: {latest_version}")

    if current_version == latest_version:
        log_message("Filebrowser is already at the latest version")
        return {"success": True, "updated": False, "version": current_version}

    # Stop service
    log_message("Stopping Filebrowser service...")
    systemctl("stop", SERVICE_NAME)

    # Create backups
    log_message("Creating backup...")
    backup_create(SERVICE_NAME, DB_PATH, ".db")
    backup_create(SERVICE_NAME, SETTINGS_PATH, ".json")

    # Cleanup old backups
    log_message("Cleaning up old backups...")
    backup_cleanup(SERVICE_NAME)

    # Update
    if not update_filebrowser():
        log_message("Update failed, restoring from backup...")
        backup_restore(SERVICE_NAME, DB_PATH, ".db")
        backup_restore(SERVICE_NAME, SETTINGS_PATH, ".json")
        systemctl("start", SERVICE_NAME)
        return {"success": False, "error": "Update failed, restored backup"}

    # Start service
    log_message("Starting Filebrowser service...")
    systemctl("start", SERVICE_NAME)

    # Wait for service to start
    time.sleep(5)

    # Check service status
    if not is_service_active(SERVICE_NAME):
        log_message("Service failed to start, restoring from backup...")
        backup_restore(SERVICE_NAME, DB_PATH, ".db")
        backup_restore(SERVICE_NAME, SETTINGS_PATH, ".json")
        systemctl("start", SERVICE_NAME)
        return {"success": False, "error": "Service failed to start, restored backup"}

    new_version = get_current_version()
    log_message("Update completed successfully!")
    log_message(f"New version: {new_version}")
    subprocess.run(["systemctl", "status", SERVICE_NAME])
    return {"success": True, "updated": True, "old_version": current_version, "new_version": new_version}

if __name__ == "__main__":
    main()
