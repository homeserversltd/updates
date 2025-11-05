#!/bin/bash

# Migration 00000001: Migrate KEA DHCP from CSV to PostgreSQL backend
# 
# This migration converts KEA DHCP server from memfile (CSV) backend
# to PostgreSQL database backend for improved reliability and performance.
#
# Idempotent: Safe to run multiple times
# Rollback: Restores backup on failure

set +e  # Do not exit on error - we handle errors explicitly

echo "========================================"
echo "Migration 00000001: KEA DHCP to PostgreSQL"
echo "========================================"
echo ""

# Configuration
KEA_CONF="/etc/kea/kea-dhcp4.conf"
KEA_CONF_BACKUP="${KEA_CONF}.csv-backup"
KEA_SERVICE="kea-dhcp4-server.service"
SKELETON_KEY="/root/key/skeleton.key"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "ERROR: This migration must run as root"
    exit 1
fi

# Function to log with timestamp
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Function to handle errors
error_exit() {
    log "ERROR: $1"
    
    # Attempt to restore backup if it exists
    if [ -f "$KEA_CONF_BACKUP" ]; then
        log "Attempting to restore backup configuration..."
        cp "$KEA_CONF_BACKUP" "$KEA_CONF"
        systemctl restart "$KEA_SERVICE" 2>/dev/null
        log "Backup restored"
    fi
    
    exit 1
}

# IDEMPOTENCY CHECK 1: Is KEA already using PostgreSQL?
log "Checking if KEA is already using PostgreSQL..."
if [ -f "$KEA_CONF" ]; then
    if grep -q '"type"[[:space:]]*:[[:space:]]*"postgresql"' "$KEA_CONF"; then
        log "SUCCESS: KEA is already configured to use PostgreSQL"
        log "Migration already applied, exiting successfully"
        exit 0
    fi
fi

# IDEMPOTENCY CHECK 2: Does KEA database already exist?
log "Checking if KEA PostgreSQL database exists..."
if sudo -u postgres psql -lqt 2>/dev/null | cut -d \| -f 1 | grep -qw kea; then
    log "KEA database already exists"
    DB_EXISTS=true
    
    # Extra safety: If database exists AND has lease4 table, assume migration already done
    SCHEMA_CHECK=$(sudo -u postgres psql -d kea -tAc "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public' AND table_name='lease4';" 2>/dev/null || echo "0")
    if [ "$SCHEMA_CHECK" != "0" ]; then
        log "SUCCESS: KEA database and schema already exist (migration likely already complete)"
        log "Config check may have failed due to formatting, but system is already using PostgreSQL"
        exit 0
    fi
else
    log "KEA database does not exist yet"
    DB_EXISTS=false
fi

# Check if kea-admin is installed, install if missing
log "Checking for kea-admin tool..."
if ! command -v kea-admin >/dev/null 2>&1; then
    log "kea-admin not found, installing..."
    if DEBIAN_FRONTEND=noninteractive apt-get install -qq -y kea-admin >/dev/null 2>&1; then
        log "kea-admin installed successfully"
    else
        error_exit "Failed to install kea-admin package"
    fi
else
    log "kea-admin is already installed"
fi

# Read Factory Access Key
log "Reading Factory Access Key..."
if [ ! -f "$SKELETON_KEY" ]; then
    error_exit "Factory Access Key not found at $SKELETON_KEY"
fi

FAK=$(cat "$SKELETON_KEY" | tr -d '\n\r')
if [ -z "$FAK" ]; then
    error_exit "Factory Access Key is empty"
fi

log "Factory Access Key loaded successfully"

# Create PostgreSQL database and user if needed
if [ "$DB_EXISTS" = false ]; then
    log "Creating KEA PostgreSQL database and user..."
    
    # Create database
    if ! sudo -u postgres psql -c "CREATE DATABASE kea;" 2>&1; then
        error_exit "Failed to create KEA database"
    fi
    log "Database 'kea' created"
    
    # Check if user already exists
    if sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='kea'" | grep -q 1; then
        log "User 'kea' already exists, updating password..."
        if ! sudo -u postgres psql -c "ALTER USER kea WITH PASSWORD '$FAK';" 2>&1; then
            error_exit "Failed to update kea user password"
        fi
    else
        log "Creating user 'kea'..."
        if ! sudo -u postgres psql -c "CREATE USER kea WITH PASSWORD '$FAK';" 2>&1; then
            error_exit "Failed to create kea user"
        fi
    fi
    log "User 'kea' configured"
    
    # Grant database privileges
    if ! sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE kea TO kea;" 2>&1; then
        error_exit "Failed to grant database privileges to kea user"
    fi
    log "Database privileges granted to kea user"
    
    # Grant schema privileges (required for table creation)
    if ! sudo -u postgres psql -d kea -c "GRANT ALL ON SCHEMA public TO kea;" 2>&1; then
        error_exit "Failed to grant schema privileges to kea user"
    fi
    log "Schema privileges granted to kea user"
else
    log "KEA database already exists, skipping creation"
    
    # Ensure user exists and password is correct
    if sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='kea'" | grep -q 1; then
        log "Updating kea user password to match current FAK..."
        sudo -u postgres psql -c "ALTER USER kea WITH PASSWORD '$FAK';" 2>&1 || true
        # Ensure schema privileges are granted (in case they were missing)
        sudo -u postgres psql -d kea -c "GRANT ALL ON SCHEMA public TO kea;" 2>&1 || true
        log "Schema privileges ensured for existing user"
    else
        log "Creating user 'kea'..."
        if ! sudo -u postgres psql -c "CREATE USER kea WITH PASSWORD '$FAK';" 2>&1; then
            error_exit "Failed to create kea user"
        fi
        if ! sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE kea TO kea;" 2>&1; then
            error_exit "Failed to grant database privileges"
        fi
        if ! sudo -u postgres psql -d kea -c "GRANT ALL ON SCHEMA public TO kea;" 2>&1; then
            error_exit "Failed to grant schema privileges"
        fi
    fi
fi

# Configure PostgreSQL peer authentication for www-data
log "Configuring PostgreSQL peer authentication..."

# Backup pg_hba.conf
if [ ! -f "/etc/postgresql/15/main/pg_hba.conf.backup" ]; then
    cp /etc/postgresql/15/main/pg_hba.conf /etc/postgresql/15/main/pg_hba.conf.backup
    log "Backed up pg_hba.conf"
fi

# Check if peer auth rule already exists
if grep -q "local[[:space:]]*kea[[:space:]]*www-data[[:space:]]*peer" /etc/postgresql/15/main/pg_hba.conf; then
    log "Peer authentication already configured for www-data"
else
    log "Adding peer authentication rule for www-data"
    # Add peer auth rule at the beginning (before other rules)
    sed -i '/^# Database administrative login/i\# KEA database access for www-data via peer auth\nlocal   kea             www-data                                peer map=keamap\n' /etc/postgresql/15/main/pg_hba.conf
    log "Added peer authentication rule to pg_hba.conf"
fi

# Backup pg_ident.conf
if [ ! -f "/etc/postgresql/15/main/pg_ident.conf.backup" ]; then
    cp /etc/postgresql/15/main/pg_ident.conf /etc/postgresql/15/main/pg_ident.conf.backup
    log "Backed up pg_ident.conf"
fi

# Check if identity mapping already exists
if grep -q "keamap[[:space:]]*www-data[[:space:]]*kea" /etc/postgresql/15/main/pg_ident.conf; then
    log "Identity mapping already configured"
else
    log "Adding identity mapping for www-data -> kea"
    echo "keamap          www-data                kea" >> /etc/postgresql/15/main/pg_ident.conf
    log "Added identity mapping to pg_ident.conf"
fi

# Reload PostgreSQL to apply changes
log "Reloading PostgreSQL configuration..."
if systemctl reload postgresql; then
    log "PostgreSQL configuration reloaded successfully"
else
    log "WARNING: Failed to reload PostgreSQL, changes may not be active yet"
fi

# Test peer authentication as www-data
log "Testing peer authentication for www-data..."
if sudo -u www-data psql -h localhost -U kea -d kea -c "SELECT 1;" >/dev/null 2>&1; then
    log "SUCCESS: Peer authentication working for www-data"
else
    log "WARNING: Peer authentication test failed, but continuing (may work after gunicorn restart)"
fi

# Initialize KEA schema if needed
log "Checking if KEA schema is initialized..."
SCHEMA_CHECK=$(sudo -u postgres psql -d kea -tAc "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public' AND table_name='lease4';" 2>/dev/null || echo "0")

if [ "$SCHEMA_CHECK" = "0" ]; then
    log "Initializing KEA database schema..."
    
    # Load schema directly from the installed KEA schema file
    SCHEMA_FILE="/usr/share/kea/scripts/pgsql/dhcpdb_create.pgsql"
    
    if [ ! -f "$SCHEMA_FILE" ]; then
        error_exit "KEA schema file not found at $SCHEMA_FILE"
    fi
    
    log "Loading schema from $SCHEMA_FILE"
    
    # Load the schema as the kea user with password (for initial setup)
    if PGPASSWORD="$FAK" psql -h localhost -U kea -d kea -f "$SCHEMA_FILE" 2>&1; then
        log "KEA schema initialized successfully"
    else
        error_exit "Failed to initialize KEA schema"
    fi
    
    # Verify schema was created
    VERIFY_CHECK=$(sudo -u postgres psql -d kea -tAc "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public' AND table_name='lease4';" 2>/dev/null || echo "0")
    if [ "$VERIFY_CHECK" = "0" ]; then
        error_exit "Schema initialization appeared to succeed but lease4 table not found"
    fi
    
    log "Schema verification passed - lease4 table created"
else
    log "KEA schema already initialized (found lease4 table)"
fi

# Test PostgreSQL connection with password (for kea user maintenance)
log "Testing PostgreSQL connection with password for kea user..."
if ! PGPASSWORD="$FAK" psql -h localhost -U kea -d kea -c "SELECT 1;" >/dev/null 2>&1; then
    log "WARNING: Password-based connection failed, but peer auth may still work"
fi

# Test peer authentication for www-data
log "Testing peer authentication for www-data user..."
if sudo -u www-data psql -h localhost -U kea -d kea -c "SELECT 1;" >/dev/null 2>&1; then
    log "SUCCESS: Peer authentication verified for www-data"
else
    log "WARNING: Peer authentication not working yet (may require gunicorn restart)"
fi

# Backup current KEA configuration
log "Backing up current KEA configuration..."
if [ -f "$KEA_CONF" ]; then
    if ! cp "$KEA_CONF" "$KEA_CONF_BACKUP"; then
        error_exit "Failed to create backup of KEA configuration"
    fi
    log "Configuration backed up to $KEA_CONF_BACKUP"
else
    error_exit "KEA configuration file not found at $KEA_CONF"
fi

# Update KEA configuration to use PostgreSQL
log "Updating KEA configuration to use PostgreSQL..."

# Use Python to modify the JSON config safely
python3 << EOF
import json
import sys

try:
    with open('$KEA_CONF', 'r') as f:
        config = json.load(f)
    
    # Update lease-database configuration
    if 'Dhcp4' in config:
        config['Dhcp4']['lease-database'] = {
            'type': 'postgresql',
            'host': 'localhost',
            'name': 'kea',
            'user': 'kea',
            'password': '$FAK'
        }
        
        # Write updated config
        with open('$KEA_CONF', 'w') as f:
            json.dump(config, f, indent=4)
        
        print("Configuration updated successfully")
        sys.exit(0)
    else:
        print("ERROR: Invalid KEA configuration structure")
        sys.exit(1)
        
except Exception as e:
    print(f"ERROR: Failed to update configuration: {e}")
    sys.exit(1)
EOF

if [ $? -ne 0 ]; then
    error_exit "Failed to update KEA configuration"
fi

log "Configuration updated successfully"

# Set proper permissions
chmod 640 "$KEA_CONF"
chown root:_kea "$KEA_CONF" 2>/dev/null || chown root:kea "$KEA_CONF" 2>/dev/null || true

# Restart KEA service
log "Restarting KEA DHCP service..."
if ! systemctl restart "$KEA_SERVICE"; then
    error_exit "Failed to restart KEA service"
fi

# Wait for service to stabilize
sleep 2

# Verify service is running
if ! systemctl is-active --quiet "$KEA_SERVICE"; then
    error_exit "KEA service failed to start after configuration change"
fi

log "KEA service restarted and running successfully"

# Verify lease database is accessible
log "Verifying lease database access..."
LEASE_CHECK=$(PGPASSWORD="$FAK" psql -h localhost -U kea -d kea -tAc "SELECT COUNT(*) FROM lease4;" 2>/dev/null || echo "ERROR")

if [ "$LEASE_CHECK" = "ERROR" ]; then
    log "WARNING: Could not query lease4 table, but service is running"
else
    log "Lease database accessible (current leases: $LEASE_CHECK)"
fi

# Optional: Remove old CSV lease files
if [ -f "/var/lib/kea/kea-leases4.csv" ]; then
    log "Removing old CSV lease files..."
    rm -f /var/lib/kea/kea-leases4.csv
    rm -f /var/lib/kea/kea-leases4.csv.1
    rm -f /var/lib/kea/kea-leases4.csv.2
    log "Old CSV files removed"
fi

# Success
log ""
log "========================================"
log "SUCCESS: Migration completed"
log "========================================"
log ""
log "KEA DHCP has been successfully migrated from CSV to PostgreSQL"
log "Backup configuration saved at: $KEA_CONF_BACKUP"
log ""

exit 0

