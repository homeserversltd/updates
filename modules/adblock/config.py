"""
Configuration for the adblock update module.
"""
from pathlib import Path

# Directory paths
UNBOUND_DIR = Path("/etc/unbound")
BLOCKLIST_PATH = UNBOUND_DIR / "blocklist.conf"
BACKUP_PATH = UNBOUND_DIR / "blocklist.conf.bak"

# Blocklist sources
STEVENBLACK_URL = "https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts"
NOTRACKING_URL = "https://raw.githubusercontent.com/notracking/hosts-blocklists/master/unbound/unbound.blacklist.conf" 