#!/bin/bash

# Base backup directory
BASE_BACKUP_DIR="/mnt/nas/backup"

# Default retention period in days
DEFAULT_RETENTION_DAYS=30

# Common logging function
log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Common backup functions
backup_create() {
    local service=$1
    local source_path=$2
    local backup_date=$(date +%Y%m%d)
    local backup_dir="$BASE_BACKUP_DIR/$service"
    
    mkdir -p "$backup_dir"
    
    if [ -f "$source_path" ]; then
        # File backup
        cp "$source_path" "$backup_dir/${service}_${backup_date}${3:-.bak}"
    elif [ -d "$source_path" ]; then
        # Directory backup
        tar -czf "$backup_dir/${service}_${backup_date}.tar.gz" -C "$source_path" .
    fi
}

backup_cleanup() {
    local service=$1
    local retention_days=${2:-$DEFAULT_RETENTION_DAYS}
    local backup_dir="$BASE_BACKUP_DIR/$service"
    
    find "$backup_dir" -name "${service}_*" -mtime "+$retention_days" -delete
}

backup_restore() {
    local service=$1
    local target_path=$2
    local backup_date=$(date +%Y%m%d)
    local backup_dir="$BASE_BACKUP_DIR/$service"
    
    if [ -f "$backup_dir/${service}_${backup_date}.tar.gz" ]; then
        # Directory restore
        rm -rf "$target_path"/*
        tar -xzf "$backup_dir/${service}_${backup_date}.tar.gz" -C "$target_path"
    elif [ -f "$backup_dir/${service}_${backup_date}.bak" ]; then
        # File restore
        cp "$backup_dir/${service}_${backup_date}.bak" "$target_path"
    fi
} 