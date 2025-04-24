#!/bin/bash

# Ensure unbound directory exists
if [ ! -d "/etc/unbound" ]; then
    echo "Error: /etc/unbound directory does not exist"
    exit 1
fi

# Create temporary working directory
TEMP_DIR=$(mktemp -d)
trap 'rm -rf "$TEMP_DIR"' EXIT
cd "$TEMP_DIR"

# Download lists with error checking
echo "Downloading blocklists..."
if ! curl -sSL --fail https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts > hosts.1; then
    echo "Warning: Failed to download StevenBlack hosts list, continuing with empty file"
    touch hosts.1
fi

if ! curl -sSL --fail https://raw.githubusercontent.com/notracking/hosts-blocklists/master/unbound/unbound.blacklist.conf > unbound.blacklist; then
    echo "Warning: Failed to download notracking blacklist, continuing with empty file"
    touch unbound.blacklist
fi

# Process the hosts file into unbound format
echo "Processing hosts file..."
if [ -s hosts.1 ]; then
    cat hosts.1 | grep '^0\.0\.0\.0' | awk '{print "local-zone: \""$2"\" always_nxdomain"}' > unbound.conf
else
    echo "Warning: hosts file empty or missing, creating empty unbound.conf"
    touch unbound.conf
fi

# Combine both lists
echo "Combining blocklists..."
cat unbound.conf unbound.blacklist | sort -u > blocklist.conf

# Backup existing blocklist if it exists
if [ -f "/etc/unbound/blocklist.conf" ]; then
    cp /etc/unbound/blocklist.conf /etc/unbound/blocklist.conf.bak
fi

# Move new blocklist into place
mv blocklist.conf /etc/unbound/blocklist.conf

# Check if unbound service exists and is active before trying to restart
if systemctl list-unit-files | grep -q unbound && systemctl is-active --quiet unbound; then
    echo "Restarting unbound service..."
    if ! systemctl restart unbound; then
        echo "Warning: Failed to restart unbound service"
        # Don't restore backup, just continue
    fi
else
    echo "Note: unbound service not active yet - skipping restart"
fi

echo "Blocklist update completed"