import os
import shutil
import tempfile
import subprocess
import requests
from pathlib import Path
from .config import UNBOUND_DIR, BLOCKLIST_PATH, BACKUP_PATH, STEVENBLACK_URL, NOTRACKING_URL


def log(msg):
    print(f"[adblock] {msg}")


def download_file(url, dest):
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        with open(dest, "wb") as f:
            f.write(r.content)
        return True
    except Exception as e:
        log(f"Warning: Failed to download {url}: {e}")
        Path(dest).touch()
        return False


def process_hosts_to_unbound(hosts_path, out_path):
    try:
        with open(hosts_path, "r") as fin, open(out_path, "w") as fout:
            for line in fin:
                if line.startswith("0.0.0.0 "):
                    parts = line.strip().split()
                    if len(parts) == 2:
                        fout.write(f'local-zone: "{parts[1]}" always_nxdomain\n')
        return True
    except Exception as e:
        log(f"Warning: Failed to process hosts file: {e}")
        Path(out_path).touch()
        return False


def combine_lists(unbound_conf, blacklist, out_path):
    try:
        with open(unbound_conf, "r") as f1, open(blacklist, "r") as f2, open(out_path, "w") as fout:
            lines = set(f1.readlines()) | set(f2.readlines())
            for line in sorted(lines):
                fout.write(line)
        return True
    except Exception as e:
        log(f"Warning: Failed to combine blocklists: {e}")
        Path(out_path).touch()
        return False


def backup_existing_blocklist():
    if BLOCKLIST_PATH.exists():
        shutil.copy2(BLOCKLIST_PATH, BACKUP_PATH)
        log(f"Backed up existing blocklist to {BACKUP_PATH}")


def move_blocklist(new_blocklist):
    shutil.move(new_blocklist, BLOCKLIST_PATH)
    log(f"Installed new blocklist at {BLOCKLIST_PATH}")


def restart_unbound():
    try:
        # Check if unbound service exists and is active
        result = subprocess.run(["systemctl", "list-unit-files"], capture_output=True, text=True)
        if "unbound" in result.stdout:
            active = subprocess.run(["systemctl", "is-active", "--quiet", "unbound"])
            if active.returncode == 0:
                log("Restarting unbound service...")
                subprocess.run(["systemctl", "restart", "unbound"], check=False)
                return
        log("Note: unbound service not active yet - skipping restart")
    except Exception as e:
        log(f"Warning: Failed to restart unbound: {e}")


def main(args=None):
    log("Starting adblock update...")
    if not UNBOUND_DIR.exists():
        log(f"Error: {UNBOUND_DIR} does not exist")
        return False
    with tempfile.TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        hosts1 = temp / "hosts.1"
        blacklist = temp / "unbound.blacklist"
        unbound_conf = temp / "unbound.conf"
        blocklist = temp / "blocklist.conf"

        log("Downloading blocklists...")
        download_file(STEVENBLACK_URL, hosts1)
        download_file(NOTRACKING_URL, blacklist)

        log("Processing hosts file...")
        if hosts1.stat().st_size > 0:
            process_hosts_to_unbound(hosts1, unbound_conf)
        else:
            log("Warning: hosts file empty or missing, creating empty unbound.conf")
            unbound_conf.touch()

        log("Combining blocklists...")
        combine_lists(unbound_conf, blacklist, blocklist)

        backup_existing_blocklist()
        move_blocklist(blocklist)
        restart_unbound()

    log("Blocklist update completed")
    return True
