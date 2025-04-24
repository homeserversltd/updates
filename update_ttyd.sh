#!/bin/bash
set -e

# Source utilities
source "$(dirname "$0")/config/utils.sh"

# Configuration
SERVICE_NAME="ttyd"
BUILD_DIR="/tmp/ttyd_build"
INSTALL_DIR="/usr/local"
TTYD_BIN="$INSTALL_DIR/bin/ttyd"

# Check mode - only verify service
if [ "$1" = "--check" ]; then
    if [ -f "/usr/local/bin/ttyd" ] && [ -x "/usr/local/bin/ttyd" ]; then
        VERSION=$(ttyd --version 2>&1 | grep -oP '\d+\.\d+\.\d+' || echo "unknown")
        if [ -n "$VERSION" ] && [ "$VERSION" != "unknown" ]; then
            LWS_VERSION=$(pkg-config --modversion libwebsockets 2>/dev/null || echo "unknown")
            log_message "OK - Current version: $VERSION (libwebsockets: $LWS_VERSION)"
            exit 0
        fi
    fi
    log_message "ttyd not found at /usr/local/bin/ttyd or not executable"
    exit 1
fi

# Get current ttyd version
CURRENT_VERSION=$(ttyd --version 2>&1 | grep -oP '\d+\.\d+\.\d+' || echo "unknown")
if [ -z "$CURRENT_VERSION" ] || [ "$CURRENT_VERSION" = "unknown" ]; then
    log_message "Failed to get current version of ttyd"
    exit 1
fi
log_message "Current ttyd version: $CURRENT_VERSION"

# Get current libwebsockets version
CURRENT_LWS_VERSION=$(pkg-config --modversion libwebsockets 2>/dev/null || echo "0.0.0")
log_message "Current libwebsockets version: $CURRENT_LWS_VERSION"

# Create temporary build directory
mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"

# Check libwebsockets update
log_message "Checking libwebsockets..."
git clone https://github.com/warmcat/libwebsockets.git
cd libwebsockets
LATEST_LWS_VERSION=$(git describe --tags --abbrev=0)

# Get latest ttyd version
cd "$BUILD_DIR"
git clone https://github.com/tsl0922/ttyd.git
cd ttyd
LATEST_VERSION=$(git describe --tags --abbrev=0)
if [ -z "$LATEST_VERSION" ]; then
    log_message "Failed to get latest version information"
    cd / && rm -rf "$BUILD_DIR"
    exit 1
fi
log_message "Latest ttyd version: $LATEST_VERSION"
log_message "Latest libwebsockets version: $LATEST_LWS_VERSION"

if [ "$CURRENT_VERSION" = "$LATEST_VERSION" ] && [ "$CURRENT_LWS_VERSION" = "$LATEST_LWS_VERSION" ]; then
    log_message "Both ttyd and libwebsockets are at their latest versions"
    cd / && rm -rf "$BUILD_DIR"
    exit 0
fi

# Stop service
log_message "Stopping ttyd service..."
systemctl stop $SERVICE_NAME

# Create backup
log_message "Creating backup..."
backup_create $SERVICE_NAME "$TTYD_BIN" ".bin"

# Cleanup old backups
log_message "Cleaning up old backups..."
backup_cleanup $SERVICE_NAME

# Update libwebsockets if needed
if [ "$CURRENT_LWS_VERSION" != "$LATEST_LWS_VERSION" ]; then
    log_message "Building libwebsockets $LATEST_LWS_VERSION..."
    cd "$BUILD_DIR/libwebsockets"
    mkdir -p build && cd build
    if ! cmake -DLWS_WITH_LIBUV=ON ..; then
        log_message "Failed to configure libwebsockets"
        backup_restore $SERVICE_NAME "$TTYD_BIN"
        systemctl start $SERVICE_NAME
        cd / && rm -rf "$BUILD_DIR"
        exit 1
    fi
    
    if ! make -j$(nproc); then
        log_message "Failed to build libwebsockets"
        backup_restore $SERVICE_NAME "$TTYD_BIN"
        systemctl start $SERVICE_NAME
        cd / && rm -rf "$BUILD_DIR"
        exit 1
    fi
    
    make install
    ldconfig
    log_message "libwebsockets updated to $LATEST_LWS_VERSION"
fi

# Build and install new ttyd version
log_message "Building ttyd $LATEST_VERSION..."
cd "$BUILD_DIR/ttyd"
mkdir -p build && cd build

if ! cmake ..; then
    log_message "Failed to configure ttyd"
    backup_restore $SERVICE_NAME "$TTYD_BIN"
    systemctl start $SERVICE_NAME
    cd / && rm -rf "$BUILD_DIR"
    exit 1
fi

if ! make -j$(nproc); then
    log_message "Failed to build ttyd"
    backup_restore $SERVICE_NAME "$TTYD_BIN"
    systemctl start $SERVICE_NAME
    cd / && rm -rf "$BUILD_DIR"
    exit 1
fi

make install

# Cleanup build directory
cd / && rm -rf "$BUILD_DIR"

# Start service
log_message "Starting ttyd service..."
systemctl start $SERVICE_NAME

# Wait for service to start
sleep 5

# Check service status
if ! systemctl is-active --quiet $SERVICE_NAME; then
    log_message "Service failed to start, restoring from backup..."
    backup_restore $SERVICE_NAME "$TTYD_BIN"
    systemctl start $SERVICE_NAME
    exit 1
fi

log_message "Update completed successfully!"
log_message "New ttyd version: $(ttyd --version 2>&1 | head -n1)"
log_message "New libwebsockets version: $(pkg-config --modversion libwebsockets)"
systemctl status $SERVICE_NAME
exit 0