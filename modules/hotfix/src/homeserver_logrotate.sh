#!/bin/bash
set -euo pipefail

LOG_FILE="/var/log/homeserver/hotfix_homeserver_logrotate.log"

INFO() {
    echo "homeserver_logrotate: $*" | tee -a "$LOG_FILE"
}

WARN() {
    echo "homeserver_logrotate: WARNING: $*" | tee -a "$LOG_FILE"
}

ERROR() {
    echo "homeserver_logrotate: ERROR: $*" | tee -a "$LOG_FILE" >&2
    exit 1
}

if [ "$EUID" -ne 0 ]; then
    ERROR "Must run as root"
fi

# Idempotent creation of logrotate config
if [ -f "/etc/logrotate.d/homeserver" ]; then
    INFO "Logrotate config /etc/logrotate.d/homeserver already exists, skipping creation"
else
    INFO "Creating logrotate config /etc/logrotate.d/homeserver"
    /bin/cat > "/etc/logrotate.d/homeserver" << 'EOF'
/var/log/homeserver/*.log {
  size 50M
  rotate 3
  compress
  missingok
  notifempty
  copytruncate
}
EOF
fi

# Idempotent creation of cron file (daily at 00:30)
if [ -f "/etc/cron.d/homeserver-logrotate" ]; then
    INFO "Cron file /etc/cron.d/homeserver-logrotate already exists, skipping creation"
else
    INFO "Creating cron file /etc/cron.d/homeserver-logrotate"
    /bin/echo "30 0 * * * root /usr/sbin/logrotate -s /var/lib/logrotate/status /etc/logrotate.d/homeserver" > "/etc/cron.d/homeserver-logrotate"
fi

# Set permissions
INFO "Setting permissions on logrotate config and cron file"
/usr/bin/chmod 644 "/etc/logrotate.d/homeserver" "/etc/cron.d/homeserver-logrotate"
/usr/sbin/chown root:root "/etc/logrotate.d/homeserver" "/etc/cron.d/homeserver-logrotate"

# Run logrotate force
INFO "Running logrotate force on /etc/logrotate.d/homeserver"
/usr/sbin/logrotate -f "/etc/logrotate.d/homeserver" && INFO "Logrotate force completed successfully" || ERROR "Logrotate force failed"