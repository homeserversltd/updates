# Forgejo update module

Forgejo Git server. Part of the **git** group: only one of `gogs` or `forgejo` runs per update cycle. The orchestrator uses ladder logic (oldest to newest by `group_order`); the first implementation with an active systemd service wins.

- **Group:** `git` (with gogs; gogs has `group_order: 1`, forgejo has `group_order: 2`)
- **service_name:** `forgejo` (systemctl is-active forgejo)
- Paths: `/opt/forgejo/forgejo`, `/opt/forgejo/custom/conf/app.ini`, etc.

Installation and migration from Gogs are handled by migration 10000000, not this module. This module handles version reporting, permissions, and (when added) upgrade-from-releases.
