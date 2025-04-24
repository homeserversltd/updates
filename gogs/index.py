import os
import subprocess
import shutil
import urllib.request
import json
import time
import tarfile
from datetime import datetime
from initialization.files.user_local_lib.updates import log_message

SERVICE_NAME = "gogs"
INSTALL_DIR = "/opt/gogs"
DATA_DIR = "/mnt/nas/git"
CONFIG_FILE = "/opt/gogs/custom/conf/app.ini"
REPO_PATH = os.path.join(DATA_DIR, "repositories")
DB_DUMP_PATH = "/tmp/gogs_db.sql"

# --- Backup/Restore/Cleanup helpers ---
def backup_create(service_name, path, ext):
    backup_path = path + ext
    try:
        if os.path.isdir(path) and ext == ".tar.gz":
            with tarfile.open(backup_path, "w:gz") as tar:
                tar.add(path, arcname=os.path.basename(path))
            log_message(f"Backup created (tar.gz) at {backup_path}")
            return backup_path
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

def backup_restore(service_name, path, ext):
    backup_path = path + ext
    try:
        if ext == ".tar.gz" and os.path.exists(backup_path):
            with tarfile.open(backup_path, "r:gz") as tar:
                tar.extractall(os.path.dirname(path))
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
    # Remove all .ini, .tar.gz, .sql backups in relevant locations
    for path, ext in [
        (CONFIG_FILE, ".ini"),
        (REPO_PATH, ".tar.gz"),
        (DB_DUMP_PATH, ".sql")
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
        gogs_bin = os.path.join(INSTALL_DIR, "gogs")
        if not os.path.isfile(gogs_bin) or not os.access(gogs_bin, os.X_OK):
            return None
        result = subprocess.run([gogs_bin, "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            parts = result.stdout.strip().split()
            if len(parts) >= 3:
                return parts[2].lstrip("v")
        return None
    except Exception:
        return None

def get_latest_version():
    try:
        with urllib.request.urlopen("https://api.github.com/repos/gogs/gogs/releases/latest") as resp:
            data = json.load(resp)
            tag = data.get("tag_name", "")
            if tag.startswith("v"):
                return tag[1:]
            return tag
    except Exception as e:
        log_message(f"Failed to get latest version info: {e}", "ERROR")
        return None

# --- DB helpers ---
def dump_db():
    try:
        result = subprocess.run(["pg_dump", "-U", "git", "gogs", "-f", DB_DUMP_PATH], capture_output=True, text=True)
        if result.returncode == 0:
            log_message(f"Database dumped to {DB_DUMP_PATH}")
            return True
        else:
            log_message(f"DB dump failed: {result.stderr}", "ERROR")
            return False
    except Exception as e:
        log_message(f"DB dump error: {e}", "ERROR")
        return False

def restore_db(backup_sql_path):
    try:
        result = subprocess.run(["psql", "-U", "git", "gogs", "-f", backup_sql_path], capture_output=True, text=True)
        if result.returncode == 0:
            log_message(f"Database restored from {backup_sql_path}")
            return True
        else:
            log_message(f"DB restore failed: {result.stderr}", "ERROR")
            return False
    except Exception as e:
        log_message(f"DB restore error: {e}", "ERROR")
        return False

# --- Update logic ---
def update_gogs():
    today = datetime.now().strftime("%Y%m%d")
    backup_dir = f"{INSTALL_DIR}_backup_{today}"
    gogs_bin = os.path.join(INSTALL_DIR, "gogs")
    # Download new version
    latest_version = get_latest_version()
    tarball_url = f"https://dl.gogs.io/{latest_version}/gogs_{latest_version}_linux_amd64.tar.gz"
    tarball_path = "/tmp/gogs.tar.gz"
    try:
        log_message(f"Downloading Gogs {latest_version}...")
        result = subprocess.run(["wget", "-q", tarball_url, "-O", tarball_path])
        if result.returncode != 0:
            log_message("Failed to download new version", "ERROR")
            return False, backup_dir
        # Backup current installation
        if os.path.exists(INSTALL_DIR):
            shutil.move(INSTALL_DIR, backup_dir)
        # Extract new version
        with tarfile.open(tarball_path, "r:gz") as tar:
            tar.extractall("/opt/")
        os.remove(tarball_path)
        log_message("Extracted new version.")
        return True, backup_dir
    except Exception as e:
        log_message(f"Update error: {e}", "ERROR")
        return False, backup_dir

def main(args=None):
    """
    Main entry point for Gogs update module.
    Args:
        args: List of arguments (supports '--check')
    Returns:
        dict: Status and results of the update
    """
    if args is None:
        args = []
    gogs_bin = os.path.join(INSTALL_DIR, "gogs")
    today = datetime.now().strftime("%Y%m%d")
    backup_dir = f"{INSTALL_DIR}_backup_{today}"

    # --check mode
    if len(args) > 0 and args[0] == "--check":
        version = get_current_version()
        if version:
            log_message(f"OK - Current version: {version}")
            return {"success": True, "version": version}
        else:
            log_message("Gogs binary not found or not executable", "ERROR")
            return {"success": False, "error": "Not found"}

    # Get current and latest version
    current_version = get_current_version()
    if not current_version:
        log_message("Failed to get current version of Gogs", "ERROR")
        return {"success": False, "error": "No current version"}
    log_message(f"Current Gogs version: {current_version}")

    latest_version = get_latest_version()
    if not latest_version:
        log_message("Failed to get latest version information", "ERROR")
        return {"success": False, "error": "No latest version"}
    log_message(f"Latest available version: {latest_version}")

    if current_version == latest_version:
        log_message("Gogs is already at the latest version")
        return {"success": True, "updated": False, "version": current_version}

    # Stop service
    log_message("Stopping Gogs service...")
    systemctl("stop", SERVICE_NAME)

    # Create backups
    log_message("Creating backups...")
    backup_create(SERVICE_NAME, CONFIG_FILE, ".ini")
    backup_create(SERVICE_NAME, REPO_PATH, ".tar.gz")
    dump_db()
    backup_create(SERVICE_NAME, DB_DUMP_PATH, ".sql")
    if os.path.exists(DB_DUMP_PATH):
        os.remove(DB_DUMP_PATH)

    # Cleanup old backups
    log_message("Cleaning up old backups...")
    backup_cleanup(SERVICE_NAME)

    # Download and install new version
    update_success, backup_dir = update_gogs()
    if not update_success:
        systemctl("start", SERVICE_NAME)
        return {"success": False, "error": "Update failed, service restarted"}

    # Restore configuration
    backup_restore(SERVICE_NAME, CONFIG_FILE, ".ini")

    # Set permissions
    try:
        subprocess.run(["chown", "-R", "git:git", INSTALL_DIR])
        subprocess.run(["chmod", "-R", "750", INSTALL_DIR])
    except Exception as e:
        log_message(f"Failed to set permissions: {e}", "WARNING")

    # Start service
    log_message("Starting Gogs service...")
    systemctl("start", SERVICE_NAME)

    # Wait for service to start
    time.sleep(5)

    # Check service status
    if not is_service_active(SERVICE_NAME):
        log_message("Service failed to start, restoring from backup...")
        if os.path.exists(INSTALL_DIR):
            shutil.rmtree(INSTALL_DIR)
        if os.path.exists(backup_dir):
            shutil.move(backup_dir, INSTALL_DIR)
        backup_restore(SERVICE_NAME, CONFIG_FILE, ".ini")
        # Restore DB
        backup_sql = f"{DB_DUMP_PATH}.sql"
        if os.path.exists(backup_sql):
            restore_db(backup_sql)
        systemctl("start", SERVICE_NAME)
        return {"success": False, "error": "Service failed to start, restored backup"}

    # Cleanup backup after successful update
    if os.path.exists(backup_dir):
        shutil.rmtree(backup_dir)

    new_version = get_current_version()
    log_message("Update completed successfully!")
    log_message(f"New version: {new_version}")
    subprocess.run(["systemctl", "status", SERVICE_NAME])
    return {"success": True, "updated": True, "old_version": current_version, "new_version": new_version}

if __name__ == "__main__":
    main()
