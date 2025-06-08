#!/bin/bash

# Convert the Python dictionary to shell variables and functions
VENV_PATHS = {
    "calibre-web": {
        "path": "/opt/calibre-web/venv",
        "packages": [
            "-r /opt/calibre-web/requirements.txt",
            "psycopg2-binary",
            "unidecode",
            "rarfile"
        ]
    },
    "libreoffice": {
        "path": "/opt/libreoffice/venv",
        "packages": [
            "unoserver"
        ],
        "system_packages": True
    },
    "mkdocs": {
        "path": "/opt/docs/venv",
        "packages": [
            "mkdocs",
            "mkdocs-material"
        ],
        "upgrade_pip": True
    },
    "flask": {
        "path": "/var/www/homeserver/venv",
        "packages": [
            "flask",
            "uwsgi",
            "netifaces",
            "psutil",
            "speedtest-cli",
            "yt-dlp",
            "schedule"
        ],
        "upgrade_pip": True,
        "system_packages": False
    }
}

# Function to update a single virtual environment
update_venv() {
    local venv_name="$1"
    local venv_path="$2"
    local packages="$3"
    local upgrade_pip="$4"
    local system_packages="$5"

    echo "Updating virtual environment: $venv_name"

    # Check if venv exists
    if [ ! -d "$venv_path" ]; then
        echo "Creating virtual environment at $venv_path"
        python3 -m venv "$venv_path"
    fi

    # Activate virtual environment
    source "$venv_path/bin/activate"

    # Upgrade pip if requested
    if [ "$upgrade_pip" = "true" ]; then
        echo "Upgrading pip..."
        pip install --upgrade pip
    fi

    # Install packages
    echo "Installing/upgrading packages..."
    if [ "$system_packages" = "true" ]; then
        pip install --upgrade --system-site-packages $packages
    else
        pip install --upgrade $packages
    fi

    deactivate
    echo "Finished updating $venv_name"
    echo "----------------------------------------"
}

# Main execution
echo "Starting virtual environment updates..."

# Update calibre-web venv
update_venv "calibre-web" \
    "/opt/calibre-web/venv" \
    "-r /opt/calibre-web/requirements.txt psycopg2-binary unidecode rarfile" \
    "false" \
    "false"

# Update libreoffice venv
update_venv "libreoffice" \
    "/opt/libreoffice/venv" \
    "unoserver" \
    "false" \
    "true"

# Update mkdocs venv
update_venv "mkdocs" \
    "/opt/docs/venv" \
    "mkdocs mkdocs-material" \
    "true" \
    "false"

# Update flask venv
update_venv "flask" \
    "/var/www/homeserver/venv" \
    "flask uwsgi netifaces psutil speedtest-cli yt-dlp schedule" \
    "true" \
    "false"

echo "All virtual environments have been updated."
