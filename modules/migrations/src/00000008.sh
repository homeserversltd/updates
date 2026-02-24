#!/bin/bash
# Migration 00000008: wan0/lan0 .link files + .network files (hotswap-resistant) + Kea drop-in on field devices.
# 1) .link files for stable interface naming (enp* only, first two by sort).
# 2) .network files with ActivationPolicy=always-up, ConfigureWithoutCarrier=yes, IgnoreCarrierLoss=yes so interfaces stay up when cables unplugged.
# 3) Kea drop-in so Kea starts after systemd-networkd-wait-online.
# Does NOT start/stop Transmission or PIA.
set -e

LOG_FILE="/var/log/homeserver/migrations.log"
NETWORK_DIR="/etc/systemd/network"
WAN_LINK_FILE="$NETWORK_DIR/10-wan0.link"
LAN_LINK_FILE="$NETWORK_DIR/20-lan0.link"
WAN_NETWORK_FILE="$NETWORK_DIR/10-wan0.network"
LAN_NETWORK_FILE="$NETWORK_DIR/20-lan0.network"

INFO() { echo "00000008: $*" | tee -a "$LOG_FILE"; }
WARN() { echo "00000008 WARNING: $*" | tee -a "$LOG_FILE" >&2; }
ERROR() { echo "00000008 ERROR: $*" | tee -a "$LOG_FILE" >&2; exit 1; }

if [ "$EUID" -ne 0 ]; then
    ERROR "Must run as root"
fi

INFO "Starting network interface link migration (.link files + .network files + Kea drop-in)"

# --- Part 1: .link files (only if either missing) ---
if [ ! -f "$WAN_LINK_FILE" ] || [ ! -f "$LAN_LINK_FILE" ]; then
    if [ ! -d "$NETWORK_DIR" ]; then
        mkdir -p "$NETWORK_DIR"
        chmod 755 "$NETWORK_DIR"
        INFO "Created $NETWORK_DIR directory"
    fi

    interfaces=()
    while IFS= read -r line; do
        if [[ $line =~ ^[0-9]+:\ ([^@]+) ]]; then
            if_name="${BASH_REMATCH[1]}"
            if [[ $if_name =~ ^enp ]] && [[ $if_name != "lo" ]] && [[ $if_name != veth* ]] && [[ $if_name != tailscale* ]] && [[ $if_name != wlan* ]]; then
                interfaces+=("$if_name")
            fi
        fi
    done < <(ip link show)

    IFS=$'\n' sorted_interfaces=($(sort <<<"${interfaces[*]}"))
    unset IFS
    selected_interfaces=("${sorted_interfaces[@]:0:2}")

    INFO "Discovered enp* interfaces: count=${#interfaces[@]} list=${interfaces[*]:-none}"
    INFO "Selected for wan0/lan0: wan0_kernel_if=${selected_interfaces[0]:-none} lan0_kernel_if=${selected_interfaces[1]:-none}"

    if [ ${#selected_interfaces[@]} -eq 0 ]; then
        ERROR "No eligible network interfaces found"
    fi

    for i in "${!selected_interfaces[@]}"; do
        if_name="${selected_interfaces[$i]}"
        if [ ! -f "/sys/class/net/$if_name/address" ]; then
            ERROR "MAC address file not found for interface $if_name"
        fi
        mac=$(cat "/sys/class/net/$if_name/address")
        if [ $i -eq 0 ]; then
            link_file="$WAN_LINK_FILE"
            stable_name="wan0"
        else
            link_file="$LAN_LINK_FILE"
            stable_name="lan0"
        fi
        INFO "Writing .link file: path=$link_file kernel_if=$if_name stable_name=$stable_name"
        cat > "$link_file" << EOF
[Match]
MACAddress=$mac

[Link]
Name=$stable_name
EOF
        chmod 644 "$link_file"
    done

    INFO "Triggering udev to apply network link changes..."
    udevadm trigger
    INFO "Network link files completed: 10-wan0.link, 20-lan0.link"
else
    INFO "Both network link files already exist, skipping .link generation"
fi

# --- Part 2: .network files (hotswap-resistant: always-up, ignore carrier) ---
if [ ! -d "$NETWORK_DIR" ]; then
    mkdir -p "$NETWORK_DIR"
    chmod 755 "$NETWORK_DIR"
    INFO "Created $NETWORK_DIR directory"
fi
INFO "Deploying hotswap-resistant .network files (ActivationPolicy=always-up, IgnoreCarrierLoss=yes)"
cat > "$WAN_NETWORK_FILE" << 'WANEOF'
[Match]
Name=wan0

[Link]
ActivationPolicy=always-up

[Network]
DHCP=yes
IPForward=yes
DNSDefaultRoute=no
DNS=127.0.0.1
ConfigureWithoutCarrier=yes
IgnoreCarrierLoss=yes

[DHCP]
RouteMetric=10
UseDNS=no
UseDomains=no
UseNTP=no
WANEOF
chmod 644 "$WAN_NETWORK_FILE"
INFO "Wrote $WAN_NETWORK_FILE"

cat > "$LAN_NETWORK_FILE" << 'LANEOF'
[Match]
Name=lan0

[Link]
ActivationPolicy=always-up

[Network]
Address=192.168.123.1/24
IPForward=yes
ConfigureWithoutCarrier=yes
IgnoreCarrierLoss=yes

[Route]
Metric=20
LANEOF
chmod 644 "$LAN_NETWORK_FILE"
INFO "Wrote $LAN_NETWORK_FILE"
if command -v networkctl &>/dev/null; then
    networkctl reload 2>/dev/null || true
    networkctl reconfigure wan0 2>/dev/null || true
    networkctl reconfigure lan0 2>/dev/null || true
    INFO "networkctl reload and reconfigure wan0/lan0 done"
fi

# --- Part 3: Kea drop-in ---
DROPIN_DIR="/etc/systemd/system/kea-dhcp4-server.service.d"
DROPIN_FILE="$DROPIN_DIR/override.conf"
if [ -f "$DROPIN_FILE" ] && grep -q "systemd-networkd-wait-online" "$DROPIN_FILE" 2>/dev/null; then
    INFO "Kea drop-in already present, skipping"
else
    INFO "Installing Kea drop-in: start after systemd-networkd-wait-online"
    mkdir -p "$DROPIN_DIR"
    cat > "$DROPIN_FILE" << 'KEAEOF'
# Start Kea only after systemd-networkd has brought interfaces up.
# Kea binds to lan0 at startup and does not retry; if lan0 is not up yet, it fails with
# "failed to open socket: the interface lan0 is not running" and never serves DHCP.
[Unit]
After=systemd-networkd-wait-online.service
Wants=systemd-networkd-wait-online.service
KEAEOF
    chmod 644 "$DROPIN_FILE"
    systemctl enable systemd-networkd-wait-online.service 2>/dev/null || true
    systemctl daemon-reload
    INFO "Kea drop-in installed; daemon-reload done"
fi

INFO "Migration 00000008 (network_interface_link + .network hotswap + Kea drop-in) completed"
exit 0
