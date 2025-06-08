import os
import subprocess
import shutil
import urllib.request
import json
import time
from initialization.files.user_local_lib.updates import log_message

INSTALL_DIR = "/opt/navidrome"
DATA_DIR = "/var/lib/navidrome"
SERVICE_NAME = "navidrome"
NAVIDROME_BIN = os.path.join(INSTALL_DIR, "navidrome")

# --- Backup/Restore/Cleanup helpers ---
def backup_create(service_name, path, ext=None):
    backup_path = path + (ext if ext else ".bak")
    try:
        if os.path.isdir(path):
            shutil.make_archive(backup_path, 'gztar', path)
            log_message(f"Backup created (tar.gz) at {backup_path}.tar.gz")
            return backup_path + ".tar.gz"
        elif os.path.exists(path):
            shutil.copy2(path, backup_path)
            log_message(f"Backup created at {backup_path}")
            return backup_path
        else:
            log_message(f"No file found to backup at {path}", "WARNING")
            return None
    except Exception as e:
        log_message(f"Failed to create backup: {e}", "ERROR")
        return None

def backup_restore(service_name, path, ext=None):
    backup_path = path + (ext if ext else ".bak")
    try:
        if backup_path.endswith('.tar.gz') and os.path.exists(backup_path):
            shutil.unpack_archive(backup_path, path)
            log_message(f"Restored backup (tar.gz) from {backup_path}")
            return True
        elif os.path.exists(backup_path):
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
    for path, ext in [
        (DATA_DIR, ".tar.gz"),
        (NAVIDROME_BIN, ".bin")
    ]:
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
        if not os.path.isfile(NAVIDROME_BIN) or not os.access(NAVIDROME_BIN, os.X_OK):
            return None
        result = subprocess.run([NAVIDROME_BIN, "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            # Output: 'Navidrome v0.49.3' or similar
            for line in result.stdout.splitlines():
                parts = line.strip().split()
                for part in parts:
                    if part[0].isdigit() and part.count('.') == 2:
                        return part
            # Fallback: third word
            parts = result.stdout.strip().split()
            if len(parts) >= 3:
                return parts[2].lstrip("v")
        return None
    except Exception:
        return None

def get_latest_version():
    try:
        with urllib.request.urlopen("https://api.github.com/repos/navidrome/navidrome/releases/latest") as resp:
            data = json.load(resp)
            tag = data.get("tag_name", "")
            if tag.startswith("v"):
                return tag[1:]
            return tag
    except Exception as e:
        log_message(f"Failed to get latest version info: {e}", "ERROR")
        return None

# --- Update logic ---
def update_navidrome():
    # TODO: Implement the actual update logic for Navidrome
    log_message("Update logic not yet implemented. Skipping actual update.", "WARNING")
    return False

def main(args=None):
    """
    Main entry point for Navidrome update module.
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
            log_message(f"Navidrome not found at {NAVIDROME_BIN} or not executable", "ERROR")
            return {"success": False, "error": "Not found"}

    # Get current and latest version
    current_version = get_current_version()
    if not current_version:
        log_message("Failed to get current version of Navidrome", "ERROR")
        return {"success": False, "error": "No current version"}
    log_message(f"Current Navidrome version: {current_version}")

    latest_version = get_latest_version()
    if not latest_version:
        log_message("Failed to get latest version information", "ERROR")
        return {"success": False, "error": "No latest version"}
    log_message(f"Latest available version: {latest_version}")

    if current_version == latest_version:
        log_message("Navidrome is already at the latest version")
        return {"success": True, "updated": False, "version": current_version}

    # Stop service
    log_message("Stopping Navidrome service...")
    systemctl("stop", SERVICE_NAME)

    # Create backups
    log_message("Creating backup...")
    backup_create(SERVICE_NAME, DATA_DIR, ".tar.gz")
    backup_create(SERVICE_NAME, NAVIDROME_BIN, ".bin")

    # Cleanup old backups
    log_message("Cleaning up old backups...")
    backup_cleanup(SERVICE_NAME)

    # Update logic (currently not implemented)
    if not update_navidrome():
        log_message("Update failed, restoring from backup...")
        backup_restore(SERVICE_NAME, DATA_DIR, ".tar.gz")
        systemctl("start", SERVICE_NAME)
        return {"success": False, "error": "Update failed, restored backup"}

    # Start service
    log_message("Starting Navidrome service...")
    systemctl("start", SERVICE_NAME)

    # Check service status
    if not is_service_active(SERVICE_NAME):
        log_message("Service failed to start, restoring from backup...")
        backup_restore(SERVICE_NAME, DATA_DIR, ".tar.gz")
        systemctl("start", SERVICE_NAME)
        return {"success": False, "error": "Service failed to start, restored backup"}

    log_message("Update completed successfully!")
    new_version = get_current_version()
    log_message(f"New version: {new_version}")
    subprocess.run(["systemctl", "status", SERVICE_NAME])
    return {"success": True, "updated": True, "old_version": current_version, "new_version": new_version}

if __name__ == "__main__":
    main()
