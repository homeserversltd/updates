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

import os
import json
import shutil
import tempfile
import subprocess
import requests
from pathlib import Path


def get_unbound_version():
    """
    Detect the currently installed Unbound version.
    Returns:
        str: Version string or None if not installed/detectable
    """
    try:
        # Try unbound -V first (most reliable)
        result = subprocess.run(["unbound", "-V"], capture_output=True, text=True, check=False)
        if result.returncode == 0:
            # Parse version from output like "Version 1.17.1"
            for line in result.stdout.split('\n'):
                if line.startswith('Version '):
                    return line.split()[1]
        
        # Fallback: try package manager version
        # Check dpkg for Debian/Ubuntu systems
        result = subprocess.run(["dpkg-query", "--showformat='${Version}'", "--show", "unbound"], 
                              capture_output=True, text=True, check=False)
        if result.returncode == 0:
            version = result.stdout.strip().strip("'")
            # Extract just the version number (remove debian package suffixes)
            if version and not version.startswith("dpkg-query"):
                # Handle versions like "1.17.1-2ubuntu0.1" -> "1.17.1"
                return version.split('-')[0]
        
        return None
    except Exception as e:
        log(f"Warning: Failed to detect Unbound version: {e}")
        return None


def update_config_version():
    """
    Update the unbound_version field in index.json with the currently installed version.
    Returns:
        bool: True if updated successfully, False otherwise
    """
    try:
        config_path = Path(__file__).parent / "index.json"
        
        # Load current config
        with open(config_path, 'r') as f:
            config_data = json.load(f)
        
        # Get current Unbound version
        current_version = get_unbound_version()
        if not current_version:
            log("Warning: Could not detect Unbound version - keeping existing config")
            return False
        
        # Update version in config
        old_version = config_data.get('metadata', {}).get('unbound_version', 'unknown')
        config_data['metadata']['unbound_version'] = current_version
        
        # Write updated config back
        with open(config_path, 'w') as f:
            json.dump(config_data, f, indent=4)
        
        if old_version != current_version:
            log(f"Updated Unbound version in config: {old_version} → {current_version}")
        else:
            log(f"Unbound version confirmed: {current_version}")
        
        return True
        
    except Exception as e:
        log(f"Warning: Failed to update config version: {e}")
        return False


def load_config():
    """Load configuration from index.json file."""
    config_path = Path(__file__).parent / "index.json"
    try:
        with open(config_path, 'r') as f:
            data = json.load(f)
        return data['config']
    except Exception as e:
        raise RuntimeError(f"Failed to load adblock configuration from {config_path}: {e}")


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
    """
    Combine blocklists with intelligent domain-level deduplication.
    Handles format inconsistencies like trailing dots and different actions.
    """
    try:
        domains = set()  # Store normalized domains
        
        def extract_domain(line):
            """Extract domain from Unbound local-zone line."""
            line = line.strip()
            if line.startswith('local-zone:'):
                # Extract domain from: local-zone: "domain.com" always_nxdomain
                parts = line.split('"')
                if len(parts) >= 2:
                    domain = parts[1].rstrip('.')  # Remove trailing dot
                    return domain.lower()  # Normalize case
            return None
        
        # Process first file (converted hosts)
        with open(unbound_conf, "r") as f1:
            for line in f1:
                domain = extract_domain(line)
                if domain:
                    domains.add(domain)
        
        # Process second file (native unbound)
        with open(blacklist, "r") as f2:
            for line in f2:
                domain = extract_domain(line)
                if domain:
                    domains.add(domain)
        
        # Write deduplicated, normalized output
        with open(out_path, "w") as fout:
            # Add header comment
            fout.write("# HOMESERVER Unified Blocklist\n")
            fout.write("# Generated by adblock module with domain-level deduplication\n")
            fout.write(f"# Total unique domains: {len(domains)}\n\n")
            
            # Write sorted, normalized entries
            for domain in sorted(domains):
                fout.write(f'local-zone: "{domain}" always_nxdomain\n')
        
        log(f"Combined and deduplicated {len(domains)} unique domains")
        return True
        
    except Exception as e:
        log(f"Warning: Failed to combine blocklists: {e}")
        Path(out_path).touch()
        return False


def backup_existing_blocklist(config):
    blocklist_path = Path(config['blocklist_path'])
    backup_path = Path(config['backup_path'])
    
    if blocklist_path.exists():
        shutil.copy2(blocklist_path, backup_path)
        log(f"Backed up existing blocklist to {backup_path}")


def move_blocklist(new_blocklist, config):
    blocklist_path = Path(config['blocklist_path'])
    shutil.move(new_blocklist, blocklist_path)
    log(f"Installed new blocklist at {blocklist_path}")


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
    # Handle command line arguments
    if args and len(args) > 0:
        if args[0] == "--version":
            version = get_unbound_version()
            if version:
                log(f"Detected Unbound version: {version}")
                return {"success": True, "version": version}
            else:
                log("Could not detect Unbound version")
                return {"success": False, "error": "Version detection failed"}
    
    log("Starting adblock update...")
    
    # Update Unbound version in configuration
    update_config_version()
    
    # Load configuration from index.json
    config = load_config()
    unbound_dir = Path(config['unbound_dir'])
    
    if not unbound_dir.exists():
        log(f"Error: {unbound_dir} does not exist")
        return False
        
    with tempfile.TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        hosts1 = temp / "hosts.1"
        blacklist = temp / "unbound.blacklist"
        unbound_conf = temp / "unbound.conf"
        blocklist = temp / "blocklist.conf"

        log("Downloading blocklists...")
        download_file(config['sources']['stevenblack'], hosts1)
        download_file(config['sources']['notracking'], blacklist)

        log("Processing hosts file...")
        if hosts1.stat().st_size > 0:
            process_hosts_to_unbound(hosts1, unbound_conf)
        else:
            log("Warning: hosts file empty or missing, creating empty unbound.conf")
            unbound_conf.touch()

        log("Combining blocklists...")
        combine_lists(unbound_conf, blacklist, blocklist)

        backup_existing_blocklist(config)
        move_blocklist(blocklist, config)
        restart_unbound()

    log("Blocklist update completed")
    return True
