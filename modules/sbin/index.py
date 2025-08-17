#!/usr/bin/env python3
"""
Sbin Module - Manage /usr/local/sbin scripts via manifest
"""
import os
import json
import hashlib
import shutil
import tempfile
from pathlib import Path
from urllib.request import urlopen
import subprocess
from typing import Dict, Any, List
from updates.index import log_message
from updates.utils.state_manager import StateManager
from updates.utils.permissions import PermissionManager, PermissionTarget, get_permissions


def sha256(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def load_config(module_dir: Path) -> Dict[str, Any]:
    with (module_dir / 'index.json').open('r') as f:
        return json.load(f)


def ensure_repo_checkout(module_dir: Path, repo_cfg: Dict[str, Any]) -> Path:
    """Clone/refresh the repo to a local cache and return its path."""
    repo_url = repo_cfg.get('url')
    branch = repo_cfg.get('branch', 'master')
    if not repo_url:
        return module_dir / 'src'
    cache_dir = module_dir / '.repo'
    try:
        if not cache_dir.exists():
            subprocess.run(['git', 'clone', '--depth', '1', '--branch', branch, repo_url, str(cache_dir)], check=True, capture_output=True)
        else:
            subprocess.run(['git', '-C', str(cache_dir), 'fetch', '--depth', '1', 'origin', branch], check=True, capture_output=True)
            subprocess.run(['git', '-C', str(cache_dir), 'reset', '--hard', f'origin/{branch}'], check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        log_message(f"git repo sync failed: {e.stderr}", 'ERROR')
        return module_dir / 'src'
    return cache_dir


def resolve_source(entry: Dict[str, Any], module_dir: Path) -> Path:
    """Return a local Path to source content, preferring repo checkout."""
    cfg = load_config(module_dir)
    repo_dir = ensure_repo_checkout(module_dir, cfg.get('repo', {}))
    candidate = repo_dir / entry['source']
    if candidate.exists():
        return candidate
    # fallback to local src
    return (module_dir / 'src' / entry['source'])


def current_permissions(path: Path) -> Dict[str, Any]:
    return get_permissions(path.as_posix())


def _dest_path(entry: Dict[str, Any]) -> Path:
    dest = entry.get('destination') or f"/usr/local/sbin/{entry['source']}"
    return Path(dest)


def check(module_dir: Path) -> Dict[str, Any]:
    def write_state(state: Dict[str, Any]) -> None:
        try:
            with (module_dir / 'manifest.state.json').open('w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            log_message(f"Failed to write sbin state: {e}", 'WARNING')

    cfg = load_config(module_dir)
    files = cfg.get('files', [])
    drift = []
    state_out = { 'files': [] }

    for entry in files:
        source = resolve_source(entry, module_dir)
        dest = _dest_path(entry)
        sha_remote = sha256(source)
        sha_dest = sha256(dest)
        mismatch = sha_remote != sha_dest
        perm_mismatch = False
        try:
            st = os.stat(dest)
            mode = int(entry.get('mode', '755'), 8)
            # only compare mode bits
            perm_mismatch = (st.st_mode & 0o777) != mode
        except FileNotFoundError:
            perm_mismatch = True
        status = {
            'destination': str(dest),
            'exists': dest.exists(),
            'content_match': not mismatch,
            'sha_remote': sha_remote,
            'sha_dest': sha_dest,
            'perm_match': not perm_mismatch,
            'managed': bool(entry.get('keepUpdated', True))
        }
        drift.append(status)
        state_out['files'].append({
            'destination': str(dest),
            'source': entry.get('source'),
            'sha_remote': sha_remote,
            'sha_dest': sha_dest,
            'managed': bool(entry.get('keepUpdated', True))
        })

    write_state(state_out)
    return { 'success': True, 'updated': False, 'drift': drift }


def apply(module_dir: Path) -> Dict[str, Any]:
    cfg = load_config(module_dir)
    files = cfg.get('files', [])
    state = StateManager('/var/backups/updates')
    perm_mgr = PermissionManager('sbin')
    changed: List[str] = []

    # Backup all destinations first
    backup_targets = [(_dest_path(f)).as_posix() for f in files]
    state.backup_module_state('sbin', description='sbin files', files=backup_targets)

    for entry in files:
        source = resolve_source(entry, module_dir)
        dest = _dest_path(entry)
        if not bool(entry.get('keepUpdated', True)):
            log_message(f"Skipping (keepUpdated=false): {dest}")
            continue

        sha_remote = sha256(source)
        sha_dest = sha256(dest)
        if sha_remote == sha_dest and dest.exists():
            # Only fix perms if they differ (defaults root:root 755)
            desired_owner = entry.get('owner','root')
            desired_group = entry.get('group','root')
            desired_mode = int(entry.get('mode','755'),8)
            cur = current_permissions(dest)
            if cur.get('owner') != desired_owner or cur.get('group') != desired_group or cur.get('mode') != desired_mode:
                perm_mgr.set_permissions([PermissionTarget(dest.as_posix(), desired_owner, desired_group, desired_mode)])
            continue

        # Replace atomically
        dest.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile('wb', delete=False, dir=dest.parent) as tmp:
            shutil.copyfile(source, tmp.name)
            tmp_path = Path(tmp.name)
        # set perms before swap
        perm_mgr.set_permissions([PermissionTarget(tmp_path.as_posix(), entry.get('owner','root'), entry.get('group','root'), int(entry.get('mode','755'),8))])
        os.replace(tmp_path, dest)
        changed.append(str(dest))
        log_message(f"Updated sbin: {dest}")

    return { 'success': True, 'updated': len(changed) > 0, 'changed': changed }


def main(args=None):
    module_dir = Path(__file__).parent
    
    # CRITICAL: Ensure module is running latest schema version before execution
    from updates.utils.module_self_update import ensure_module_self_updated
    if not ensure_module_self_updated(module_dir):
        return {"success": False, "error": "Module self-update failed"}
    
    # Now run with latest code
    if args and '--check' in args:
        return check(module_dir)
    return apply(module_dir)


