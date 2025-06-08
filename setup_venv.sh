#!/bin/bash
# Setup script for updates system virtual environment

set -e

UPDATES_DIR="/usr/local/lib/user_local_lib/updates"
VENV_DIR="$UPDATES_DIR/venv"
REQUIREMENTS_FILE="$UPDATES_DIR/requirements.txt"

echo "Setting up virtual environment for updates system..."

# Create virtual environment if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment at $VENV_DIR"
    python3 -m venv "$VENV_DIR"
else
    echo "Virtual environment already exists at $VENV_DIR"
fi

# Activate virtual environment and install/upgrade packages
echo "Installing/upgrading packages..."
source "$VENV_DIR/bin/activate"

# Upgrade pip first
pip install --upgrade pip

# Install requirements
if [ -f "$REQUIREMENTS_FILE" ]; then
    pip install -r "$REQUIREMENTS_FILE"
else
    echo "Warning: requirements.txt not found at $REQUIREMENTS_FILE"
fi

echo "Virtual environment setup complete!"
echo "To activate: source $VENV_DIR/bin/activate"
echo "To run updates: $VENV_DIR/bin/python $UPDATES_DIR/index.py" 