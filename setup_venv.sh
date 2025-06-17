#!/bin/bash
# Setup script for updates system virtual environment
# This script is idempotent and safe to run multiple times

set -e

UPDATES_DIR="/usr/local/lib/updates"
VENV_DIR="$UPDATES_DIR/venv"
REQUIREMENTS_FILE="$UPDATES_DIR/requirements.txt"
VENV_PYTHON="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"
UPDATE_MANAGER_SCRIPT="$UPDATES_DIR/updateManager.sh"
SBIN_SYMLINK="/usr/local/sbin/updateManager"

echo "Setting up virtual environment for updates system..."

# Function to check if virtual environment is functional
check_venv_health() {
    if [ -f "$VENV_PYTHON" ] && [ -x "$VENV_PYTHON" ]; then
        # Test if Python in venv is working
        if "$VENV_PYTHON" -c "import sys; print('Python OK')" >/dev/null 2>&1; then
            return 0
        fi
    fi
    return 1
}

# Function to get installed package version
get_package_version() {
    local package="$1"ls
    if [ -f "$VENV_PIP" ]; then
        "$VENV_PIP" show "$package" 2>/dev/null | grep "^Version:" | cut -d' ' -f2
    fi
}

# Create or recreate virtual environment if needed
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment at $VENV_DIR"
    python3 -m venv "$VENV_DIR"
elif ! check_venv_health; then
    echo "Virtual environment exists but appears corrupted, recreating..."
    rm -rf "$VENV_DIR"
    python3 -m venv "$VENV_DIR"
else
    echo "Virtual environment already exists and is functional at $VENV_DIR"
fi

# Verify venv was created successfully
if ! check_venv_health; then
    echo "Error: Failed to create functional virtual environment"
    exit 1
fi

# Activate virtual environment and install/upgrade packages
echo "Installing/upgrading packages..."

# Check current pip version
CURRENT_PIP_VERSION=$(get_package_version "pip")
echo "Current pip version: ${CURRENT_PIP_VERSION:-'not installed'}"

# Upgrade pip (safe to run multiple times)
echo "Upgrading pip..."
"$VENV_PIP" install --upgrade pip --quiet

NEW_PIP_VERSION=$(get_package_version "pip")
if [ "$CURRENT_PIP_VERSION" != "$NEW_PIP_VERSION" ]; then
    echo "Pip upgraded: $CURRENT_PIP_VERSION -> $NEW_PIP_VERSION"
else
    echo "Pip already up to date: $NEW_PIP_VERSION"
fi

# Install/upgrade requirements
if [ -f "$REQUIREMENTS_FILE" ]; then
    echo "Processing requirements from $REQUIREMENTS_FILE"
    
    # Use --upgrade to ensure latest versions, but only if needed
    # The --quiet flag reduces output noise on repeated runs
    "$VENV_PIP" install --upgrade -r "$REQUIREMENTS_FILE" --quiet
    
    echo "Requirements installation/upgrade completed"
    
    # Show installed packages for verification
    echo "Installed packages:"
    "$VENV_PIP" list --format=freeze
else
    echo "Warning: requirements.txt not found at $REQUIREMENTS_FILE"
    echo "Skipping package installation"
fi

# Final health check
if check_venv_health; then
    echo "✓ Virtual environment setup complete and verified!"
else
    echo "✗ Virtual environment setup failed verification"
    exit 1
fi

# Create symlink for updateManager.sh in /usr/local/sbin
echo "Setting up updateManager symlink..."
if [ -f "$UPDATE_MANAGER_SCRIPT" ]; then
    # Remove existing symlink if it exists
    if [ -L "$SBIN_SYMLINK" ]; then
        echo "Removing existing symlink at $SBIN_SYMLINK"
        rm "$SBIN_SYMLINK"
    elif [ -f "$SBIN_SYMLINK" ]; then
        echo "Warning: File exists at $SBIN_SYMLINK (not a symlink), backing up..."
        mv "$SBIN_SYMLINK" "${SBIN_SYMLINK}.backup.$(date +%s)"
    fi
    
    # Create the symlink
    echo "Creating symlink: $SBIN_SYMLINK -> $UPDATE_MANAGER_SCRIPT"
    ln -s "$UPDATE_MANAGER_SCRIPT" "$SBIN_SYMLINK"
    
    # Verify symlink was created successfully
    if [ -L "$SBIN_SYMLINK" ] && [ -x "$SBIN_SYMLINK" ]; then
        echo "✓ updateManager symlink created successfully"
    else
        echo "✗ Failed to create updateManager symlink"
        exit 1
    fi
else
    echo "Warning: updateManager.sh not found at $UPDATE_MANAGER_SCRIPT"
    echo "Skipping symlink creation"
fi

echo ""
echo "Usage information:"
echo "  To activate: source $VENV_DIR/bin/activate"
echo "  To run updates: $VENV_PYTHON $UPDATES_DIR/index.py"
echo "  Direct execution: $VENV_DIR/bin/python $UPDATES_DIR/index.py"
echo "  System command: updateManager [--check|--legacy|--help]" 