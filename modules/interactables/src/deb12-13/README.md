# deb12-13: Debian 12 → 13 in-place upgrade (infinite-index)

## Overview

In-place upgrade from Bookworm to Trixie. Config in `index.json`; orchestrator in `index.py`. Entry point is `../debian12_to_13.py` (fractalization: loads this module by path, runs orchestrator).

## Structure

- `index.json`: metadata, paths (log_file, backup_dir, sources_list, sources_d, kea_conf, kea_patch_script), execution, config (id, backports_line, backports_filename).
- `index.py`: Orchestrator; loads config, resolves paths, runs steps sequentially (backup APT, remove backports, sed bookworm→trixie, patch Kea DHCP4, apt full-upgrade, add trixie-backports, cleanup).

## Paths

All paths are in `index.json` under `paths`. Resolved at runtime with `expandvars`. Kea patch script is sibling of this directory: `src/kea_dhcp4_add_subnet_id.py`.

## Execution

Orchestrator validates root and `lsb_release -cs` = bookworm, then runs steps in order. Logs to `paths.log_file`. Exit 0 on success, 1 on fatal error.
