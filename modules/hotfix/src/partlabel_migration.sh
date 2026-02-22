#!/bin/bash
# Apply PARTLABELs to system partitions on an existing install (retrofit).
# Detects system disk from root mount, applies homeserver-* labels 1-6.
# Idempotent: skips if homeserver-root already has a label on the disk.
set -euo pipefail

LOG_FILE="/var/log/homeserver/hotfix_partlabel_migration.log"

INFO() { echo "partlabel_migration: $*" | tee -a "$LOG_FILE"; }
WARN() { echo "partlabel_migration: WARNING: $*" | tee -a "$LOG_FILE"; }
ERROR() { echo "partlabel_migration: ERROR: $*" | tee -a "$LOG_FILE" >&2; exit 1; }

if [ "$EUID" -ne 0 ]; then
    ERROR "Must run as root"
fi

# System partition labels in preseed order (1=EFI, 2=boot, 3=swap, 4=vault, 5=deploy, 6=root)
LABELS=( "homeserver-boot-efi" "homeserver-boot" "homeserver-swap" "homeserver-vault" "homeserver-deploy" "homeserver-root" )

# 1. Find system disk from root mount
ROOT_SOURCE=$(findmnt -n -o SOURCE / 2>/dev/null) || true
if [ -z "$ROOT_SOURCE" ] || [ ! -b "$ROOT_SOURCE" ]; then
    ERROR "Could not determine root mount source (findmnt /)"
fi

# Strip partition to get disk (e.g. /dev/sda6 -> /dev/sda, /dev/nvme0n1p6 -> /dev/nvme0n1)
if [[ "$ROOT_SOURCE" =~ nvme.*p[0-9]+ ]]; then
    DISK="${ROOT_SOURCE%p*}"
else
    DISK="${ROOT_SOURCE%%[0-9]*}"
fi

if [ -z "$DISK" ] || [ ! -b "$DISK" ]; then
    ERROR "Could not derive disk from root source $ROOT_SOURCE (got: $DISK)"
fi

INFO "System disk: $DISK (from root $ROOT_SOURCE)"

# 2. Optional: skip if already labeled (idempotent)
if [ -e "/dev/disk/by-partlabel/homeserver-root" ]; then
    EXISTING=$(readlink -f /dev/disk/by-partlabel/homeserver-root 2>/dev/null)
    if [ "$EXISTING" = "$ROOT_SOURCE" ]; then
        INFO "PARTLABELs already applied (homeserver-root present), skipping"
        exit 0
    fi
fi

# 3. Require sgdisk
if ! command -v sgdisk &>/dev/null; then
    ERROR "sgdisk not found (install gdisk)"
fi

# 4. Apply PARTLABELs 1-6
for i in {1..6}; do
    LABEL="${LABELS[$((i-1))]}"
    INFO "Setting partition $i to PARTLABEL: $LABEL"
    if ! sgdisk -c "$i:$LABEL" "$DISK"; then
        ERROR "sgdisk -c $i:$LABEL $DISK failed"
    fi
done

# 5. Trigger udev so by-partlabel symlinks appear
if command -v udevadm &>/dev/null; then
    udevadm trigger --subsystem-match=block 2>/dev/null || true
    sleep 1
fi

# 6. Verify
MISSING=""
for LABEL in "${LABELS[@]}"; do
    if [ ! -e "/dev/disk/by-partlabel/$LABEL" ]; then
        MISSING="$MISSING $LABEL"
    fi
done
if [ -n "$MISSING" ]; then
    WARN "Some symlinks missing after apply:$MISSING"
else
    INFO "All PARTLABELs verified: $(ls /dev/disk/by-partlabel/homeserver-* 2>/dev/null | tr '\n' ' ')"
fi

INFO "Partlabel migration completed successfully"
exit 0
