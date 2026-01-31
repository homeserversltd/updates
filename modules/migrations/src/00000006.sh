#!/bin/bash

# Migration 00000006: Migrate HOMESERVER frontend from Create React App to Vite
#
# This migration completes the CRA-to-Vite build tool transition across the
# HOMESERVER platform suite. Field units receiving updated inject (or this
# migration) get: package.json updated for Vite, vite.config.ts created,
# public/index.html adjusted for Vite entry, then npm install, npm run build,
# and Gunicorn restart. Output remains in build/; Flask contract unchanged.
#
# Idempotent: Safe to run multiple times (exits early if already on Vite)
# Conditional: Only applies to systems with HOMESERVER frontend installed

set +e  # Do not exit on error - we handle errors explicitly

echo "========================================"
echo "Migration 00000006: CRA to Vite Frontend Build"
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

# Configuration (server paths; inject content lives at webroot)
WEBROOT="/var/www/homeserver"
PACKAGE_JSON="${WEBROOT}/package.json"
VITE_CONFIG="${WEBROOT}/vite.config.ts"
INDEX_HTML="${WEBROOT}/public/index.html"

# IDEMPOTENCY CHECK 1: Is HOMESERVER frontend installed?
log "Checking if HOMESERVER frontend is installed..."
if [ ! -f "$PACKAGE_JSON" ]; then
    log "SUCCESS: HOMESERVER frontend not installed on this system"
    log "Migration not applicable, exiting successfully"
    exit 0
fi

# IDEMPOTENCY CHECK 2: Already on Vite?
if [ -f "$VITE_CONFIG" ] && ! grep -q '"react-scripts"' "$PACKAGE_JSON" 2>/dev/null; then
    log "Vite already in use (vite.config.ts present, no react-scripts)"
    log "SUCCESS: Migration already applied, exiting successfully"
    exit 0
fi

# At this point: either no vite.config.ts or package.json still has react-scripts
# Apply full migration (file changes + npm install + build + restart)

log "Applying CRA to Vite migration..."

# --- Step 0: Backup files before modification (rollback: copy back from BACKUP_DIR) ---
BACKUP_DIR="/var/log/homeserver/migration-00000006-$(date +%Y%m%d%H%M%S)"
log "Creating backup in $BACKUP_DIR..."
mkdir -p "$BACKUP_DIR"
cp -a "$PACKAGE_JSON" "$BACKUP_DIR/package.json" 2>/dev/null || true
cp -a "$INDEX_HTML" "$BACKUP_DIR/public_index.html" 2>/dev/null || true
[ -f "$VITE_CONFIG" ] && cp -a "$VITE_CONFIG" "$BACKUP_DIR/vite.config.ts" 2>/dev/null || true
log "Backup created"

# --- Step 1: Update package.json for Vite ---
log "Updating package.json for Vite..."

# Remove react-scripts and CRA-related devDependencies (if present)
if grep -q '"react-scripts"' "$PACKAGE_JSON" 2>/dev/null; then
    sed -i '/"react-scripts":/d' "$PACKAGE_JSON"
    sed -i '/"@testing-library\/react":/d' "$PACKAGE_JSON"
    sed -i '/"@testing-library\/jest-dom":/d' "$PACKAGE_JSON"
    sed -i '/"@testing-library\/user-event":/d' "$PACKAGE_JSON"
    sed -i '/"eslint-config-react-app":/d' "$PACKAGE_JSON"
    log "Removed react-scripts and CRA-related entries"
fi
# Remove vestigial Babel devDependency (CRA-era)
sed -i '/"@babel\/plugin-proposal-private-property-in-object":/d' "$PACKAGE_JSON" 2>/dev/null || true

# Update scripts: start -> dev, build -> vite build + post_build_tab_restore
if grep -q '"start": "react-scripts start"' "$PACKAGE_JSON" 2>/dev/null; then
    sed -i 's/"start": "react-scripts start"/"dev": "vite"/' "$PACKAGE_JSON"
fi
if grep -q '"build": "react-scripts build"' "$PACKAGE_JSON" 2>/dev/null; then
    sed -i 's|"build": "react-scripts build"|"build": "vite build \&\& (if [ -f premium/utils/post_build_tab_restore.py ]; then python3 premium/utils/post_build_tab_restore.py; else echo \"[post-build-tabs] premium utils not present, skipping\"; fi)"|' "$PACKAGE_JSON"
fi
if grep -q '"test": "react-scripts test"' "$PACKAGE_JSON" 2>/dev/null; then
    sed -i 's/"test": "react-scripts test"/"test": "echo \\\"Vite-based tests not yet configured\\\""/' "$PACKAGE_JSON"
fi
sed -i '/"eject": "react-scripts eject"/d' "$PACKAGE_JSON" 2>/dev/null || true

# Add vite and @vitejs/plugin-react if missing
if ! grep -q '"vite":' "$PACKAGE_JSON" 2>/dev/null; then
    # Insert after first "dependencies" entry (after opening brace or first key)
    sed -i '/"dependencies": {/a\        "vite": "^5.0.0",' "$PACKAGE_JSON"
fi
if ! grep -q '"@vitejs/plugin-react":' "$PACKAGE_JSON" 2>/dev/null; then
    sed -i '/"@floating-ui\/react":/a\        "@vitejs/plugin-react": "^4.0.0",' "$PACKAGE_JSON"
fi
if ! grep -q '"fast-deep-equal":' "$PACKAGE_JSON" 2>/dev/null; then
    sed -i '/"react-dom":/a\        "fast-deep-equal": "^3.1.3",' "$PACKAGE_JSON"
fi

log "package.json updated"

# --- Step 2: Create vite.config.ts ---
log "Creating vite.config.ts..."
cat > "$VITE_CONFIG" << 'VITEEOF'
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  root: 'public',
  plugins: [react()],
  build: {
    outDir: 'build',
  },
  define: {
    'process.env.NODE_ENV': JSON.stringify(process.env.NODE_ENV || 'production'),
  },
});
VITEEOF
log "vite.config.ts created"

# --- Step 3: Ensure public/index.html has Vite entry ---
if [ -f "$INDEX_HTML" ]; then
    log "Checking public/index.html for Vite entry..."
    if ! grep -q 'type="module".*src=.*index.tsx' "$INDEX_HTML" 2>/dev/null; then
        # Remove old CRA script tags if present
        sed -i '/<script defer="defer" src="\/static\/js\/main.*.js"><\/script>/d' "$INDEX_HTML"
        # Add Vite module entry before </body>
        if grep -q '<div id="root"></div>' "$INDEX_HTML"; then
            sed -i 's|<div id="root"></div>|<div id="root"></div>\n    <script type="module" src="/src/index.tsx"></script>|' "$INDEX_HTML"
        else
            sed -i '/<\/body>/i \    <script type="module" src="/src/index.tsx"></script>' "$INDEX_HTML"
        fi
        log "public/index.html updated for Vite entry"
    else
        log "public/index.html already has Vite entry"
    fi
else
    log "WARNING: public/index.html not found; build may fail"
fi

# --- Step 4: npm install ---
log "Running npm install (this may take a while)..."
cd "$WEBROOT" || { log "ERROR: Cannot cd to $WEBROOT"; exit 1; }
if ! npm install --no-audit --no-fund; then
    log "ERROR: npm install failed"
    exit 1
fi
log "npm install completed"

# --- Step 5: npm run build ---
log "Running npm run build..."
if ! npm run build; then
    log "ERROR: npm run build failed"
    exit 1
fi
log "npm run build completed"

# --- Step 6: Restart Gunicorn ---
log "Restarting Gunicorn service..."
if systemctl list-unit-files --type=service 2>/dev/null | grep -q 'gunicorn'; then
    if systemctl restart gunicorn.service 2>/dev/null || systemctl restart gunicorn 2>/dev/null; then
        log "Gunicorn restarted successfully"
    else
        log "WARNING: Gunicorn restart failed (frontend built; may need manual restart)"
    fi
else
    log "Gunicorn service not found (skip restart)"
fi

# Success
log ""
log "========================================"
log "SUCCESS: Migration completed"
log "========================================"
log ""
log "HOMESERVER frontend now uses Vite (build output in build/)"
log "Contract unchanged: npm run build, Flask serves build/"
log "Pre-migration backup (if full migration ran): $BACKUP_DIR"
log ""

exit 0
