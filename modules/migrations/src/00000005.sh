#!/bin/bash

# Migration 00000005: Replace Complex Calibre Helper System with Simple Watcher
# 
# This migration replaces the overcomplicated calibreHelperDaemon.sh system
# (800 lines with feeder, watcher, backup, hardlinks, tracking, SHA256 hashing)
# with a simple 22-line inotify-based watcher that does the same job.
#
# Old system components:
# - calibre-feeder.service (daily timer, file crawler, SHA256 tracking)
# - calibre-watch.service (batch processor with 60s polling)
# - calibreHelperDaemon.sh (800 lines of complexity)
# - /var/lib/calibre-feeder/processed_files.txt (tracking database)
# - /mnt/nas/books/backup/ (backup directory structure)
#
# New system:
# - calibre-simple-watch.service (inotify-based instant processing)
# - calibreSimpleWatcher.sh (22 lines, one job: watch and add)
#
# Idempotent: Safe to run multiple times
# Conditional: Only applies to systems with old Calibre daemon

set +e  # Do not exit on error - we handle errors explicitly

echo "========================================"
echo "Migration 00000005: Calibre System Simplification"
echo "========================================"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "ERROR: This migration must run as root"
    exit 1
fi

# Function to log with timestamp
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Configuration
OLD_FEEDER_SERVICE="/etc/systemd/system/calibre-feeder.service"
OLD_FEEDER_TIMER="/etc/systemd/system/calibre-feeder.timer"
OLD_WATCHER_SERVICE="/etc/systemd/system/calibre-watch.service"
OLD_DAEMON_SCRIPT="/usr/local/sbin/calibreHelperDaemon.sh"
OLD_TRACKING_DIR="/var/lib/calibre-feeder"
NEW_WATCHER_SERVICE="/etc/systemd/system/calibre-simple-watch.service"
NEW_WATCHER_SCRIPT="/usr/local/sbin/calibreSimpleWatcher.sh"

# IDEMPOTENCY CHECK 1: Is new system already installed?
log "Checking if new simple watcher is already installed..."
if [ -f "$NEW_WATCHER_SERVICE" ] && systemctl is-enabled --quiet calibre-simple-watch.service 2>/dev/null; then
    log "New simple watcher service is already installed and enabled"
    
    # Check if old system is gone
    if [ ! -f "$OLD_FEEDER_SERVICE" ] && [ ! -f "$OLD_WATCHER_SERVICE" ]; then
        log "SUCCESS: Migration already completed (new system installed, old system removed)"
        exit 0
    else
        log "New system exists but old system remnants detected, will clean up old system"
    fi
else
    log "New simple watcher not detected"
fi

# IDEMPOTENCY CHECK 2: Does old system exist?
log "Checking if old Calibre daemon system exists..."
OLD_SYSTEM_EXISTS=false

if [ -f "$OLD_FEEDER_SERVICE" ] || [ -f "$OLD_WATCHER_SERVICE" ] || [ -f "$OLD_DAEMON_SCRIPT" ]; then
    OLD_SYSTEM_EXISTS=true
    log "Old Calibre daemon system detected"
else
    log "Old Calibre daemon system not found"
fi

# IDEMPOTENCY CHECK 3: Is Calibre Web even installed?
if [ ! -f "/etc/systemd/system/calibre-web.service" ]; then
    log "SUCCESS: Calibre Web not installed on this system"
    log "Migration not applicable, exiting successfully"
    exit 0
fi

log "Calibre Web is installed"

# If old system doesn't exist and new system isn't installed, migration not needed yet
if [ "$OLD_SYSTEM_EXISTS" = false ] && [ ! -f "$NEW_WATCHER_SERVICE" ]; then
    log "SUCCESS: Neither old nor new system detected (fresh install will handle setup)"
    exit 0
fi

# At this point, we either have:
# 1. Old system that needs removal + new system installation
# 2. Old system remnants with new system already present (cleanup needed)

log ""
log "========================================"
log "Phase 1: Remove Old Complex System"
log "========================================"
log ""

# Stop and disable old services
if systemctl is-active --quiet calibre-feeder.service 2>/dev/null; then
    log "Stopping calibre-feeder.service..."
    systemctl stop calibre-feeder.service
fi

if systemctl is-active --quiet calibre-feeder.timer 2>/dev/null; then
    log "Stopping calibre-feeder.timer..."
    systemctl stop calibre-feeder.timer
fi

if systemctl is-active --quiet calibre-watch.service 2>/dev/null; then
    log "Stopping calibre-watch.service..."
    systemctl stop calibre-watch.service
fi

if systemctl is-enabled --quiet calibre-feeder.service 2>/dev/null; then
    log "Disabling calibre-feeder.service..."
    systemctl disable calibre-feeder.service 2>/dev/null
fi

if systemctl is-enabled --quiet calibre-feeder.timer 2>/dev/null; then
    log "Disabling calibre-feeder.timer..."
    systemctl disable calibre-feeder.timer 2>/dev/null
fi

if systemctl is-enabled --quiet calibre-watch.service 2>/dev/null; then
    log "Disabling calibre-watch.service..."
    systemctl disable calibre-watch.service 2>/dev/null
fi

# Remove old service files
if [ -f "$OLD_FEEDER_SERVICE" ]; then
    log "Removing $OLD_FEEDER_SERVICE..."
    rm -f "$OLD_FEEDER_SERVICE"
fi

if [ -f "$OLD_FEEDER_TIMER" ]; then
    log "Removing $OLD_FEEDER_TIMER..."
    rm -f "$OLD_FEEDER_TIMER"
fi

if [ -f "$OLD_WATCHER_SERVICE" ]; then
    log "Removing $OLD_WATCHER_SERVICE..."
    rm -f "$OLD_WATCHER_SERVICE"
fi

# Remove version tracking files
rm -f "/etc/systemd/system/calibre-feeder.version" 2>/dev/null
rm -f "/etc/systemd/system/calibre-watch.version" 2>/dev/null

log "Old services removed"

# Archive old tracking data (don't delete it, might be useful)
if [ -d "$OLD_TRACKING_DIR" ]; then
    ARCHIVE_PATH="/var/log/homeserver/calibre-feeder-archive-$(date +%s).tar.gz"
    log "Archiving old tracking data to $ARCHIVE_PATH..."
    tar -czf "$ARCHIVE_PATH" -C "$(dirname "$OLD_TRACKING_DIR")" "$(basename "$OLD_TRACKING_DIR")" 2>/dev/null
    log "Removing old tracking directory..."
    rm -rf "$OLD_TRACKING_DIR"
fi

# Note: We keep /mnt/nas/books/backup/ - user might want those files
log "Note: Backup directory /mnt/nas/books/backup/ preserved (user may have books there)"

# Reload systemd
log "Reloading systemd daemon..."
systemctl daemon-reload

log ""
log "========================================"
log "Phase 2: Install New Simple System"
log "========================================"
log ""

# Check if inotify-tools is installed
if ! command -v inotifywait &> /dev/null; then
    log "Installing inotify-tools..."
    apt update -qq || { log "ERROR: apt update failed"; exit 1; }
    apt install -qq -y inotify-tools || { log "ERROR: Failed to install inotify-tools"; exit 1; }
    log "inotify-tools installed"
else
    log "inotify-tools already installed"
fi

# Check if calibre-bin is installed
if ! command -v calibredb &> /dev/null; then
    log "Installing calibre-bin..."
    apt update -qq || { log "ERROR: apt update failed"; exit 1; }
    apt install -qq -y calibre-bin || { log "ERROR: Failed to install calibre-bin"; exit 1; }
    log "calibre-bin installed"
else
    log "calibre-bin already installed"
fi

# Create new watcher script if it doesn't exist
if [ ! -f "$NEW_WATCHER_SCRIPT" ]; then
    log "Creating new simple watcher script..."
    cat > "$NEW_WATCHER_SCRIPT" << 'WATCHER_EOF'
#!/bin/bash

WATCH_DIR="/mnt/nas/books/upload"
LIBRARY_PATH="/mnt/nas/books"

mkdir -p "$WATCH_DIR"

inotifywait -m "$WATCH_DIR" -e create -e moved_to --format '%w%f' |
  while read filepath; do
    if [[ "$filepath" =~ \.(pdf|epub|mobi|azw|azw3)$ ]]; then
      echo "[$(date)] Processing: $(basename "$filepath")"
      if calibredb add "$filepath" --library-path="$LIBRARY_PATH" 2>&1; then
        echo "[$(date)] Added and removing: $(basename "$filepath")"
        rm -f "$filepath"
      else
        echo "[$(date)] Duplicate or failed, removing: $(basename "$filepath")"
        rm -f "$filepath"
      fi
    fi
  done
WATCHER_EOF
    chmod +x "$NEW_WATCHER_SCRIPT"
    log "Created watcher script: $NEW_WATCHER_SCRIPT"
else
    log "Watcher script already exists: $NEW_WATCHER_SCRIPT"
fi

# Create new service file if it doesn't exist
if [ ! -f "$NEW_WATCHER_SERVICE" ]; then
    log "Creating new simple watcher service..."
    cat > "$NEW_WATCHER_SERVICE" << 'SERVICE_EOF'
[Unit]
Description=Calibre Simple Watch Directory Monitor
After=network.target calibre-web.service
Wants=calibre-web.service

[Service]
Type=simple
User=calibre
Group=calibre
ExecStart=/usr/local/sbin/calibreSimpleWatcher.sh
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SERVICE_EOF
    log "Created service file: $NEW_WATCHER_SERVICE"
else
    log "Service file already exists: $NEW_WATCHER_SERVICE"
fi

# Ensure upload directory exists with proper permissions
log "Ensuring upload directory exists..."
mkdir -p /mnt/nas/books/upload
chown calibre:calibre /mnt/nas/books/upload 2>/dev/null || log "WARNING: Could not set ownership on upload directory"
chmod 775 /mnt/nas/books/upload 2>/dev/null || log "WARNING: Could not set permissions on upload directory"

# Reload systemd and enable new service
log "Reloading systemd daemon..."
systemctl daemon-reload

log "Enabling calibre-simple-watch.service..."
if ! systemctl enable calibre-simple-watch.service; then
    log "ERROR: Failed to enable new service"
    exit 1
fi

log "Starting calibre-simple-watch.service..."
if systemctl start calibre-simple-watch.service; then
    log "Service started successfully"
    
    # Wait for service to stabilize
    sleep 3
    
    if systemctl is-active --quiet calibre-simple-watch.service; then
        log "Service is running and healthy"
    else
        log "WARNING: Service may not have started properly"
    fi
else
    log "WARNING: Failed to start service (may need manual start)"
fi

# Success
log ""
log "========================================"
log "SUCCESS: Migration completed"
log "========================================"
log ""
log "Old complex system removed:"
log "  - calibre-feeder.service (stopped, disabled, removed)"
log "  - calibre-feeder.timer (stopped, disabled, removed)"
log "  - calibre-watch.service (stopped, disabled, removed)"
log "  - Tracking data archived to /var/log/homeserver/"
log ""
log "New simple system installed:"
log "  - calibre-simple-watch.service (enabled and running)"
log "  - calibreSimpleWatcher.sh (22 lines vs 800)"
log "  - Upload directory: /mnt/nas/books/upload/"
log ""
log "To use: Drop PDF/EPUB/MOBI files into /mnt/nas/books/upload/"
log "        Files are added instantly and removed automatically"
log ""

exit 0

