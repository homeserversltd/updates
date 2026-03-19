#!/bin/bash
set -euo pipefail

LOG_FILE="/var/log/homeserver/hotfix_homeserver_flat_service_symlinks.log"

log_info() {
    echo "homeserver_flat_service_symlinks: $*" | tee -a "$LOG_FILE"
}

log_error() {
    echo "homeserver_flat_service_symlinks: ERROR: $*" | tee -a "$LOG_FILE" >&2
    exit 1
}

if [ "${EUID}" -ne 0 ]; then
    log_error "Must run as root"
fi

pick_postgres_version() {
    if [ ! -d "/etc/postgresql" ]; then
        return 1
    fi
    local versions=()
    while IFS= read -r line; do
        versions+=("$line")
    done < <(/usr/bin/find /etc/postgresql -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | /usr/bin/sort -Vr)

    local v
    for v in "${versions[@]}"; do
        if [ -d "/etc/postgresql/${v}/main" ] && [ -d "/usr/lib/postgresql/${v}/bin" ]; then
            echo "$v"
            return 0
        fi
    done

    return 1
}

pick_php_version() {
    if [ ! -d "/etc/php" ]; then
        return 1
    fi

    local candidates=()
    while IFS= read -r line; do
        candidates+=("$line")
    done < <(/usr/bin/find /etc/php -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | /usr/bin/sort -Vr)

    local v
    for v in "${candidates[@]}"; do
        if [ -d "/etc/php/${v}/fpm/pool.d" ] && [ -f "/etc/php/${v}/fpm/pool.d/piwigo.conf" ]; then
            echo "$v"
            return 0
        fi
    done

    for v in "${candidates[@]}"; do
        if [ -d "/etc/php/${v}/fpm/pool.d" ]; then
            echo "$v"
            return 0
        fi
    done

    return 1
}

ensure_postgres_symlinks() {
    local pg_version
    if ! pg_version="$(pick_postgres_version)"; then
        log_error "Could not find a valid PostgreSQL version under /etc/postgresql"
    fi

    local main_dir="/etc/postgresql/${pg_version}/main"
    local bin_dir="/usr/lib/postgresql/${pg_version}/bin"
    local flat_root="/opt/homeserver/postgresql"

    /usr/bin/mkdir -p "${flat_root}"
    /usr/bin/ln -sfn "${main_dir}" "${flat_root}/current"
    /usr/bin/ln -sfn "${bin_dir}" "${flat_root}/bin"

    if [ ! -d "${flat_root}/current" ] || [ ! -x "${flat_root}/bin/postgres" ]; then
        log_error "PostgreSQL flat symlink validation failed"
    fi

    log_info "PostgreSQL flat symlinks OK -> ${pg_version}"
}

ensure_php_symlinks() {
    local php_version
    if ! php_version="$(pick_php_version)"; then
        log_error "Could not find a valid PHP-FPM version under /etc/php"
    fi

    local etc_php="/etc/php/${php_version}"
    local php_fpm_bin=""

    if [ -x "/usr/sbin/php-fpm${php_version}" ]; then
        php_fpm_bin="/usr/sbin/php-fpm${php_version}"
    elif [ -x "/usr/sbin/php${php_version}-fpm" ]; then
        php_fpm_bin="/usr/sbin/php${php_version}-fpm"
    else
        log_error "PHP-FPM binary not found for ${php_version} (tried php-fpm${php_version}, php${php_version}-fpm)"
    fi

    local flat_root="/opt/homeserver/php-fpm"
    /usr/bin/mkdir -p "${flat_root}/bin"
    /usr/bin/ln -sfn "${etc_php}" "${flat_root}/current"
    /usr/bin/ln -sfn "${php_fpm_bin}" "${flat_root}/bin/php-fpm"

    if [ ! -d "${flat_root}/current/fpm/pool.d" ] || [ ! -x "${flat_root}/bin/php-fpm" ]; then
        log_error "PHP-FPM flat symlink validation failed"
    fi

    log_info "PHP-FPM flat symlinks OK -> ${php_version}"
}

ensure_postgres_symlinks
ensure_php_symlinks
log_info "Flat service symlink hotfix completed successfully"
