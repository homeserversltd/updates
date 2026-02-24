#!/bin/bash
# Migration 00000007: Apply PARTLABELs (homeserver-*) to system partitions on existing installs.
# Detects system disk from root mount, applies labels 1-6. Idempotent: skips if homeserver-root present.
set -euo pipefail

LOG_FILE="/var/log/homeserver/migrations.log"
INFO()  { echo "00000007: $*" | tee -a "$LOG_FILE"; }
WARN()  { echo "00000007 WARNING: $*" | tee -a "$LOG_FILE" >&2; }
ERROR() { echo "00000007 ERROR: $*" | tee -a "$LOG_FILE" >&2; exit 1; }

if [ "$EUID" -ne 0 ]; then
    ERROR "Must run as root"
fi

LABELS=( "homeserver-boot-efi" "homeserver-boot" "homeserver-swap" "homeserver-vault" "homeserver-deploy" "homeserver-root" )

ROOT_SOURCE=$(findmnt -n -o SOURCE / 2>/dev/null) || true
if [ -z "$ROOT_SOURCE" ] || [ ! -b "$ROOT_SOURCE" ]; then
    ERROR "Could not determine root mount source (findmnt /)"
fi

if [[ "$ROOT_SOURCE" =~ nvme.*p[0-9]+ ]]; then
    DISK="${ROOT_SOURCE%p*}"
else
    DISK="${ROOT_SOURCE%%[0-9]*}"
fi

if [ -z "$DISK" ] || [ ! -b "$DISK" ]; then
    ERROR "Could not derive disk from root source $ROOT_SOURCE (got: $DISK)"
fi

INFO "System disk: $DISK (from root $ROOT_SOURCE)"

if [ -e "/dev/disk/by-partlabel/homeserver-root" ]; then
    EXISTING=$(readlink -f /dev/disk/by-partlabel/homeserver-root 2>/dev/null)
    if [ "$EXISTING" = "$ROOT_SOURCE" ]; then
        INFO "PARTLABELs already applied (homeserver-root present), skipping"
        exit 0
    fi
fi

if ! command -v sgdisk &>/dev/null; then
    ERROR "sgdisk not found (install gdisk)"
fi

for i in {1..6}; do
    LABEL="${LABELS[$((i-1))]}"
    INFO "Setting partition $i to PARTLABEL: $LABEL"
    if ! sgdisk -c "$i:$LABEL" "$DISK"; then
        ERROR "sgdisk -c $i:$LABEL $DISK failed"
    fi
done

if command -v udevadm &>/dev/null; then
    udevadm trigger --subsystem-match=block 2>/dev/null || true
    sleep 1
fi

MISSING=""
for LABEL in "${LABELS[@]}"; do
    if [ ! -e "/dev/disk/by-partlabel/$LABEL" ]; then
        MISSING="$MISSING $LABEL"
    fi
done
if [ -n "$MISSING" ]; then
    WARN "Some symlinks missing after apply:$MISSING"
else
    INFO "All PARTLABELs verified"
fi

INFO "Migration 00000007 (partlabel) completed successfully"
exit 0
