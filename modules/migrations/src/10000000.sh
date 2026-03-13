#!/bin/bash
# Migration 10000000: Migrate Gogs to Forgejo (full replacement).
# 1) Stop and disable Gogs; remove Gogs SSH block from sshd_config.
# 2) Install Forgejo if not present (binary, dirs, PostgreSQL forgejo DB, app.ini, systemd, SSH block), start and create admin user.
# Idempotent: if Forgejo is already running and Gogs is gone, exit 0.
# Repo data: use clone_all_repos_from_api (from Gogs) then push_all_repos_to_forgejo separately if needed.
#
# Post-migration (handoff): Do not edit /home/git/.ssh/authorized_keys or insert keys via psql; Forgejo is the gatekeeper.
# Add SSH keys via Forgejo UI (Settings -> SSH / GPG Keys) or: sudo -u git /opt/forgejo/forgejo admin auth add-key (when available).
# Resync keys after UI changes: sudo -u git /opt/forgejo/forgejo admin regenerate keys --config /opt/forgejo/custom/conf/app.ini
#
# Woodpecker OAuth: If using Woodpecker CI (ci.home.arpa), register an OAuth2 application in Forgejo (Settings -> Applications):
#   Redirect URI: https://ci.home.arpa/authorize
#   Use WOODPECKER_FORGEJO_* (not GITEA_*) in Woodpecker .env and docker-compose; the Forgejo driver requires FORGEJO_* to populate client_id.
#   Compose must have extra_hosts "git.home.arpa:host-gateway" so the server container can reach Forgejo. On the server, nftables must allow Docker:
#   input 172.17.0.0/16 and 172.18.0.0/16 tcp dport 443; forward those subnets to lan/wan (otherwise /authorize will 504).
set -e

LOG_FILE="/var/log/homeserver/migrations.log"
SSHD_CONFIG="/etc/ssh/sshd_config"
FORGEJO_VERSION="14.0.2"
FORGEJO_URL="https://codeberg.org/forgejo/forgejo/releases/download/v${FORGEJO_VERSION}/forgejo-${FORGEJO_VERSION}-linux-amd64"
ADMIN_USER="${ADMIN_USER:-owner}"

INFO() { echo "10000000: $*" | tee -a "$LOG_FILE"; }
WARN() { echo "10000000 WARNING: $*" | tee -a "$LOG_FILE" >&2; }
ERROR() { echo "10000000 ERROR: $*" | tee -a "$LOG_FILE" >&2; exit 1; }

if [ "$EUID" -ne 0 ]; then
    ERROR "Must run as root"
fi

# --- Idempotency: already migrated? ---
if systemctl is-active --quiet forgejo 2>/dev/null && ! systemctl is-active --quiet gogs 2>/dev/null; then
    if [ -x /opt/forgejo/forgejo ] && grep -q "AuthorizedKeysCommand /opt/forgejo/forgejo" "$SSHD_CONFIG" 2>/dev/null; then
        INFO "Forgejo already running and Gogs stopped; migration already applied"
        exit 0
    fi
fi

# --- Step 1: Stop and disable Gogs ---
if systemctl list-unit-files --full 2>/dev/null | grep -q '^gogs\.service'; then
    INFO "Stopping and disabling Gogs"
    systemctl stop gogs 2>/dev/null || true
    systemctl disable gogs 2>/dev/null || true
else
    INFO "Gogs service not installed, skipping stop/disable"
fi

# --- Step 2: Remove Gogs SSH block ---
if [ -f "$SSHD_CONFIG" ]; then
    if grep -q "AuthorizedKeysCommand /opt/gogs/gogs" "$SSHD_CONFIG" 2>/dev/null; then
        INFO "Removing Gogs SSH block from sshd_config"
        cp "$SSHD_CONFIG" "${SSHD_CONFIG}.bak.10000000"
        # Remove block from "# Gogs SSH configuration" through the following "    X11Forwarding no" (Gogs block only)
        sed -i '/# Gogs SSH configuration/,/^[[:space:]]*X11Forwarding no[[:space:]]*$/d' "$SSHD_CONFIG"
        # If Gogs block had no comment, it may remain; user can remove manually or add comment and re-run
        INFO "Restarting sshd"
        systemctl restart sshd
    else
        INFO "No Gogs SSH block found in sshd_config"
    fi
fi

# --- Step 3: If Forgejo already installed, ensure running and SSH block present ---
if [ -x /opt/forgejo/forgejo ]; then
    INFO "Forgejo binary present; ensuring service and SSH config"
    if ! grep -q "AuthorizedKeysCommand /opt/forgejo/forgejo" "$SSHD_CONFIG" 2>/dev/null; then
        INFO "Adding Forgejo SSH block to sshd_config"
        cat >> "$SSHD_CONFIG" << 'SSHEOF'

# Forgejo SSH configuration
Match User git
    AuthorizedKeysCommand /opt/forgejo/forgejo serv key --config=/opt/forgejo/custom/conf/app.ini %k
    AuthorizedKeysCommandUser git
    PasswordAuthentication no
    AllowTcpForwarding no
    X11Forwarding no
SSHEOF
        systemctl restart sshd
    fi
    systemctl enable forgejo 2>/dev/null || true
    systemctl start forgejo 2>/dev/null || true
    INFO "Migration 10000000 (Gogs to Forgejo) completed (Forgejo already installed)"
    exit 0
fi

# --- Step 4: Full Forgejo install ---
INFO "Installing Forgejo from scratch"

# 4.1 User and groups
useradd -m -d /home/git -s /bin/bash git 2>/dev/null || true
if ! id -u git >/dev/null 2>&1; then
    ERROR "Failed to ensure git user exists"
fi
usermod -aG git www-data 2>/dev/null || true
usermod -aG git "$ADMIN_USER" 2>/dev/null || true

# 4.2 Download binary
INFO "Downloading Forgejo binary"
if ! wget -q "$FORGEJO_URL" -O /tmp/forgejo.bin --timeout=120 2>/dev/null; then
    ERROR "Failed to download Forgejo binary"
fi
mkdir -p /opt/forgejo
mv /tmp/forgejo.bin /opt/forgejo/forgejo
chmod +x /opt/forgejo/forgejo
chown -R git:git /opt/forgejo

# 4.3 Directories
for path in /home/git/.ssh /var/log/forgejo /opt/forgejo/custom/conf /opt/forgejo/data /opt/forgejo/repositories; do
    mkdir -p "$path"
    chown git:git "$path"
done
chmod 700 /home/git/.ssh
chmod 755 /var/log/forgejo
chmod 750 /opt/forgejo/custom/conf /opt/forgejo/data /opt/forgejo/repositories
touch /home/git/.ssh/authorized_keys
chown git:git /home/git/.ssh/authorized_keys
chmod 600 /home/git/.ssh/authorized_keys

# 4.4 Database (FAK)
PG_PASS="changeme"
[ -f /root/key/skeleton.key ] && PG_PASS=$(cat /root/key/skeleton.key | tr -d '\n')
SECRET=$(openssl rand -base64 32 2>/dev/null | tr -d '\n') || SECRET="changeme"

sudo -u postgres psql -c "CREATE USER git WITH PASSWORD '$PG_PASS';" 2>/dev/null || true
sudo -u postgres psql -c "ALTER USER git WITH PASSWORD '$PG_PASS';" 2>/dev/null || true
sudo -u postgres psql -c "CREATE DATABASE forgejo WITH OWNER git ENCODING 'UTF8';" 2>/dev/null || true
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE forgejo TO git;" 2>/dev/null || true
sudo -u postgres psql -d forgejo -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;" 2>/dev/null || true
sudo -u postgres psql -d forgejo -c "ALTER SCHEMA public OWNER TO git;" 2>/dev/null || true

# 4.5 app.ini (escape single quotes in PG_PASS and SECRET for use in heredoc)
PG_ESC=$(echo "$PG_PASS" | sed "s/'/''/g")
SEC_ESC=$(echo "$SECRET" | sed "s/'/''/g")
cat > /opt/forgejo/custom/conf/app.ini << INIEOF
APP_NAME = Home Git Server
RUN_USER = git
RUN_MODE = prod

[database]
DB_TYPE  = postgres
HOST     = 127.0.0.1:5432
NAME     = forgejo
USER     = git
PASSWD   = ${PG_ESC}
SSL_MODE = disable

[repository]
ROOT = /opt/forgejo/repositories
ENABLE_LOCAL_PATH_MIGRATION = true

[server]
PROTOCOL         = http
DOMAIN           = git.home.arpa
HTTP_ADDR        = 127.0.0.1
HTTP_PORT        = 3000
ROOT_URL         = https://git.home.arpa/
LOCAL_ROOT_URL   = http://localhost:3000/
DISABLE_SSH      = false
SSH_ALLOW_UNEXPECTED_AUTHORIZED_KEYS = true
SSH_PORT         = 22
START_SSH_SERVER = false
OFFLINE_MODE     = false
EXTERNAL_URL     = https://git.home.arpa/

[mailer]
ENABLED = false

[service]
REGISTER_EMAIL_CONFIRM = false
ENABLE_NOTIFY_MAIL     = false
DISABLE_REGISTRATION   = true
ENABLE_CAPTCHA         = false
REQUIRE_SIGNIN_VIEW    = true

[picture]
DISABLE_GRAVATAR        = true
ENABLE_FEDERATED_AVATAR = false

[session]
PROVIDER = file

[log]
MODE      = file
LEVEL     = Info
ROOT_PATH = /var/log/forgejo

[security]
INSTALL_LOCK = true
SECRET_KEY   = ${SEC_ESC}
INIEOF
chown git:git /opt/forgejo/custom/conf/app.ini
chmod 640 /opt/forgejo/custom/conf/app.ini

# 4.6 systemd
cat > /etc/systemd/system/forgejo.service << 'SVCEOF'
[Unit]
Description=Forgejo Git Server
After=network.target postgresql.service

[Service]
Type=simple
User=git
Group=git
WorkingDirectory=/opt/forgejo
ExecStart=/opt/forgejo/forgejo web --config /opt/forgejo/custom/conf/app.ini
Restart=always
Environment=USER=git HOME=/home/git FORGEJO_WORK_DIR=/opt/forgejo

[Install]
WantedBy=multi-user.target
SVCEOF
chmod 644 /etc/systemd/system/forgejo.service
systemctl daemon-reload
systemctl enable forgejo

# 4.7 SSH block (Forgejo)
if ! grep -q "AuthorizedKeysCommand /opt/forgejo/forgejo" "$SSHD_CONFIG" 2>/dev/null; then
    INFO "Adding Forgejo SSH block to sshd_config"
    cat >> "$SSHD_CONFIG" << 'SSHEOF'

# Forgejo SSH configuration
Match User git
    AuthorizedKeysCommand /opt/forgejo/forgejo serv key --config=/opt/forgejo/custom/conf/app.ini %k
    AuthorizedKeysCommandUser git
    PasswordAuthentication no
    AllowTcpForwarding no
    X11Forwarding no
SSHEOF
    systemctl restart sshd
fi

# 4.8 Start and admin user
systemctl start forgejo
sleep 5
if [ -f /root/key/skeleton.key ]; then
    PW=$(cat /root/key/skeleton.key | tr -d '\n')
    sudo -u git env FORGEJO_WORK_DIR=/opt/forgejo /opt/forgejo/forgejo --config /opt/forgejo/custom/conf/app.ini admin user create --name="$ADMIN_USER" --password="$PW" --email="${ADMIN_USER}@home.arpa" --admin=true 2>/dev/null || true
fi

INFO "Migration 10000000 (Gogs to Forgejo) completed. Forgejo: https://git.home.arpa"
INFO "Post-migration: add SSH keys via Forgejo UI only; if using Woodpecker, create OAuth app in Forgejo (redirect https://ci.home.arpa/authorize), set WOODPECKER_FORGEJO_* in Woodpecker .env, ensure compose has extra_hosts for git.home.arpa and server nftables allows Docker (input 443, forward to lan/wan)"
exit 0
