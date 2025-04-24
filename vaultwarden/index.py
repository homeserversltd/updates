import os
import subprocess
import shutil
import tarfile
import urllib.request
import json
import time
from initialization.files.user_local_lib.updates import log_message

SERVICE_NAME = "vaultwarden"
DATA_DIR = "/var/lib/vaultwarden"
CONFIG_FILE = "/etc/vaultwarden.env"
VAULTWARDEN_BIN = "/opt/vaultwarden/vaultwarden"
WEB_VAULT_DIR = "/opt/vaultwarden/web-vault"
LOG_DIR = "/var/log/vaultwarden"
ATTACHMENTS_DIR = "/mnt/nas/vaultwarden/attachments"

# --- Backup/Restore/Cleanup helpers ---
def backup_create(service_name, path, ext=None):
    if ext is None:
        ext = ".bak"
    backup_path = path + ext
    try:
        if os.path.isdir(path) and ext.endswith(".tar.gz"):
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

def backup_restore(service_name, path, ext=None):
    if ext is None:
        ext = ".bak"
    backup_path = path + ext
    try:
        if ext.endswith(".tar.gz") and os.path.exists(backup_path):
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
    for path, ext in [
        (DATA_DIR, ".tar.gz"),
        (CONFIG_FILE, ".env"),
        (VAULTWARDEN_BIN, ".bin"),
        (WEB_VAULT_DIR, "_web.tar.gz"),
        (LOG_DIR, "_logs.tar.gz"),
        (ATTACHMENTS_DIR, "_attachments.tar.gz")
    ]:
        backup_path = path + ext
        try:
            if os.path.exists(backup_path):
                if os.path.isdir(backup_path):
                    shutil.rmtree(backup_path)
                else:
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
        if not os.path.isfile(VAULTWARDEN_BIN) or not os.access(VAULTWARDEN_BIN, os.X_OK):
            return None
        result = subprocess.run([VAULTWARDEN_BIN, "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                parts = line.strip().split()
                for part in parts:
                    if part[0].isdigit() and part.count('.') == 2:
                        return part
            parts = result.stdout.strip().split()
            if len(parts) >= 2:
                return parts[1].lstrip("v")
        return None
    except Exception:
        return None

def get_latest_version():
    try:
        with urllib.request.urlopen("https://api.github.com/repos/dani-garcia/vaultwarden/releases/latest") as resp:
            data = json.load(resp)
            tag = data.get("tag_name", "")
            if tag.startswith("v"):
                return tag[1:]
            return tag
    except Exception as e:
        log_message(f"Failed to get latest version info: {e}", "ERROR")
        return None

def get_latest_web_version():
    try:
        with urllib.request.urlopen("https://api.github.com/repos/dani-garcia/bw_web_builds/releases/latest") as resp:
            data = json.load(resp)
            tag = data.get("tag_name", "")
            return tag
    except Exception as e:
        log_message(f"Failed to get latest web vault version info: {e}", "ERROR")
        return None

# --- Update logic ---
def update_vaultwarden():
    # Install new version using cargo
    log_message("Installing new version...")
    env = os.environ.copy()
    env["CARGO_HOME"] = "/usr/local/cargo"
    env["PATH"] = "/usr/local/cargo/bin:" + env.get("PATH", "")
    result = subprocess.run(["cargo", "install", "vaultwarden", "--features", "postgresql"], env=env, capture_output=True, text=True)
    if result.returncode != 0:
        log_message(f"Failed to build/install vaultwarden: {result.stderr}", "ERROR")
        return False
    # Copy binary to system location
    try:
        shutil.copy2(os.path.expanduser("~/.cargo/bin/vaultwarden"), VAULTWARDEN_BIN)
        os.chmod(VAULTWARDEN_BIN, 0o755)
        subprocess.run(["chown", "vaultwarden:vaultwarden", VAULTWARDEN_BIN])
    except Exception as e:
        log_message(f"Failed to copy binary to system location: {e}", "ERROR")
        return False
    # Update web vault
    log_message("Updating web vault...")
    latest_web_version = get_latest_web_version()
    if not latest_web_version:
        log_message("Failed to get latest web vault version", "ERROR")
        return False
    try:
        if os.path.exists(WEB_VAULT_DIR):
            shutil.rmtree(WEB_VAULT_DIR)
        os.makedirs(WEB_VAULT_DIR, exist_ok=True)
        tarball_url = f"https://github.com/dani-garcia/bw_web_builds/releases/download/{latest_web_version}/bw_web_{latest_web_version}.tar.gz"
        tarball_path = "/tmp/web_vault.tar.gz"
        result = subprocess.run(["curl", "-L", tarball_url, "-o", tarball_path])
        if result.returncode != 0:
            log_message("Failed to download web vault", "ERROR")
            return False
        with tarfile.open(tarball_path, "r:gz") as tar:
            tar.extractall(WEB_VAULT_DIR)
        os.remove(tarball_path)
        subprocess.run(["chown", "-R", "vaultwarden:vaultwarden", WEB_VAULT_DIR])
    except Exception as e:
        log_message(f"Failed to update web vault: {e}", "ERROR")
        return False
    return True

def main(args=None):
    """
    Main entry point for Vaultwarden update module.
    Args:
        args: List of arguments (supports '--check')
    Returns:
        dict: Status and results of the update
    """
    if args is None:
        args = []

    # --check mode
    if len(args) > 0 and args[0] == "--check":
        # Try multiple version methods
        version = get_current_version()
        if version:
            log_message(f"OK - Current version: {version}")
            return {"success": True, "version": version}
        log_message(f"Vaultwarden not found at {VAULTWARDEN_BIN} or not executable", "ERROR")
        return {"success": False, "error": "Not found"}

    # Get current and latest version
    current_version = get_current_version()
    if not current_version:
        log_message("Failed to get current version of Vaultwarden", "ERROR")
        return {"success": False, "error": "No current version"}
    log_message(f"Current Vaultwarden version: {current_version}")

    latest_version = get_latest_version()
    if not latest_version:
        log_message("Failed to get latest version information", "ERROR")
        return {"success": False, "error": "No latest version"}
    log_message(f"Latest available version: {latest_version}")

    if current_version == latest_version:
        log_message("Vaultwarden is already at the latest version")
        return {"success": True, "updated": False, "version": current_version}

    # Stop service
    log_message("Stopping Vaultwarden service...")
    systemctl("stop", SERVICE_NAME)

    # Create backups
    log_message("Creating backup...")
    backup_create(SERVICE_NAME, DATA_DIR, ".tar.gz")
    backup_create(SERVICE_NAME, CONFIG_FILE, ".env")
    backup_create(SERVICE_NAME, VAULTWARDEN_BIN, ".bin")
    backup_create(SERVICE_NAME, WEB_VAULT_DIR, "_web.tar.gz")
    backup_create(SERVICE_NAME, LOG_DIR, "_logs.tar.gz")
    backup_create(SERVICE_NAME, ATTACHMENTS_DIR, "_attachments.tar.gz")

    # Cleanup old backups
    log_message("Cleaning up old backups...")
    backup_cleanup(SERVICE_NAME)

    # Update Vaultwarden
    if not update_vaultwarden():
        log_message("Failed to update vaultwarden, restoring from backup...")
        backup_restore(SERVICE_NAME, DATA_DIR, ".tar.gz")
        backup_restore(SERVICE_NAME, CONFIG_FILE, ".env")
        backup_restore(SERVICE_NAME, VAULTWARDEN_BIN, ".bin")
        backup_restore(SERVICE_NAME, WEB_VAULT_DIR, "_web.tar.gz")
        backup_restore(SERVICE_NAME, LOG_DIR, "_logs.tar.gz")
        backup_restore(SERVICE_NAME, ATTACHMENTS_DIR, "_attachments.tar.gz")
        systemctl("start", SERVICE_NAME)
        return {"success": False, "error": "Update failed, restored backup"}

    # Start service
    log_message("Starting Vaultwarden service...")
    systemctl("start", SERVICE_NAME)

    # Wait for service to start
    time.sleep(5)

    # Check service status
    if not is_service_active(SERVICE_NAME):
        log_message("Service failed to start, restoring from backup...")
        backup_restore(SERVICE_NAME, DATA_DIR, ".tar.gz")
        backup_restore(SERVICE_NAME, CONFIG_FILE, ".env")
        backup_restore(SERVICE_NAME, VAULTWARDEN_BIN, ".bin")
        backup_restore(SERVICE_NAME, WEB_VAULT_DIR, "_web.tar.gz")
        backup_restore(SERVICE_NAME, LOG_DIR, "_logs.tar.gz")
        backup_restore(SERVICE_NAME, ATTACHMENTS_DIR, "_attachments.tar.gz")
        systemctl("start", SERVICE_NAME)
        return {"success": False, "error": "Service failed to start, restored backup"}

    log_message("Update completed successfully!")
    new_version = get_current_version()
    log_message(f"New version: {new_version}")
    subprocess.run(["systemctl", "status", SERVICE_NAME])
    return {"success": True, "updated": True, "old_version": current_version, "new_version": new_version}

if __name__ == "__main__":
    main()
