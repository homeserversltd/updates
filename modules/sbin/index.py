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
from typing import Dict, Any, List, Tuple, Optional
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
    
    # Set environment to prevent credential prompts
    env = os.environ.copy()
    env['GIT_TERMINAL_PROMPT'] = '0'
    
    try:
        if not cache_dir.exists():
            log_message(f"[SBIN] Cloning repository {repo_url} (branch: {branch}) to {cache_dir}")
            subprocess.run(['git', 'clone', '--depth', '1', '--branch', branch, repo_url, str(cache_dir)], 
                         check=True, capture_output=True, stdin=subprocess.DEVNULL, env=env)
        else:
            log_message(f"[SBIN] Fetching updates from {repo_url} (branch: {branch})")
            subprocess.run(['git', '-C', str(cache_dir), 'fetch', '--depth', '1', 'origin', branch], 
                         check=True, capture_output=True, stdin=subprocess.DEVNULL, env=env)
            subprocess.run(['git', '-C', str(cache_dir), 'reset', '--hard', f'origin/{branch}'], 
                         check=True, capture_output=True, stdin=subprocess.DEVNULL, env=env)
    except subprocess.CalledProcessError as e:
        log_message(f"[SBIN] git repo sync failed: {e.stderr}", 'ERROR')
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
    
    # Check if version update is needed
    update_needed, remote_version = _check_version_update_needed()
    
    enabled_files = [f for f in files if bool(f.get('keepUpdated', True))]
    
    log_message(f"Sbin module status: {len(enabled_files)} enabled files")
    
    # Basic file existence check
    drift = []
    for entry in enabled_files:
        dest = _dest_path(entry)
        drift.append({
            'destination': str(dest),
            'exists': dest.exists(),
            'managed': True
        })

    # Persist state with version info
    state_out = { 
        'files': enabled_files,
        'total_files': len(files),
        'enabled_files': len(enabled_files),
        'update_needed': update_needed,
        'remote_version': remote_version
    }
    
    write_state(state_out)
    return { 
        'success': True, 
        'updated': update_needed, 
        'drift': drift, 
        'enabled_files': len(enabled_files),
        'version': remote_version
    }


def _check_version_update_needed() -> Tuple[bool, Optional[str]]:
    """
    Check if an update is needed by comparing local content_version with remote VERSION file.
    
    Returns:
        Tuple[bool, Optional[str]]: (update_needed, remote_version)
    """
    try:
        # Load local config to get content_version
        module_dir = Path(__file__).parent
        cfg = load_config(module_dir)
        local_version = cfg.get('metadata', {}).get('content_version', '0.0.0')
        
        log_message(f"Local content version: {local_version}")
        
        # Get remote version from repository
        repo_cfg = cfg.get('repo', {})
        if not repo_cfg.get('url'):
            log_message("No repository URL configured, assuming update needed", "WARNING")
            return True, None
        
        # Clone repository temporarily to check remote version
        temp_dir = tempfile.mkdtemp(prefix="sbin_version_check_")
        try:
            # Shallow clone just for version check
            log_message(f"[SBIN] Cloning repository for version check: {repo_cfg['url']} (branch: {repo_cfg.get('branch', 'master')})")
            env = os.environ.copy()
            env['GIT_TERMINAL_PROMPT'] = '0'
            clone_success = subprocess.run([
                'git', 'clone', 
                '--branch', repo_cfg.get('branch', 'master'),
                '--depth', '1',
                repo_cfg['url'],
                temp_dir
            ], capture_output=True, text=True, stdin=subprocess.DEVNULL, env=env, check=True)
            
            # Read remote VERSION file
            remote_version_file = os.path.join(temp_dir, "VERSION")
            if not os.path.exists(remote_version_file):
                log_message("Remote VERSION file not found, assuming update needed", "WARNING")
                return True, None
            
            with open(remote_version_file, 'r') as f:
                remote_version = f.read().strip()
            
            log_message(f"Remote version: {remote_version}")
            
            # Compare versions
            if local_version == remote_version:
                log_message("Local content version matches remote version, no update needed")
                return False, remote_version
            else:
                log_message(f"Version mismatch: local {local_version} vs remote {remote_version}, update needed")
                return True, remote_version
                
        finally:
            # Always cleanup temp directory
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
                
    except Exception as e:
        log_message(f"Version check failed: {e}, assuming update needed", "WARNING")
        return True, None


def _update_local_version(module_dir: Path, new_version: str) -> None:
    """
    Update the local index.json content_version to match the remote version.
    This prevents unnecessary re-runs of the same update.
    """
    try:
        config_path = module_dir / 'index.json'
        with config_path.open('r') as f:
            config = json.load(f)
        
        # Update the content_version
        config['metadata']['content_version'] = new_version
        
        # Write back the updated config
        with config_path.open('w') as f:
            json.dump(config, f, indent=2)
        
        log_message(f"Updated local content_version to {new_version}")
        
    except Exception as e:
        log_message(f"Failed to update local version: {e}", "WARNING")


def apply(module_dir: Path) -> Dict[str, Any]:
    cfg = load_config(module_dir)
    files = cfg.get('files', [])
    state = StateManager('/var/backups/updates')
    perm_mgr = PermissionManager('sbin')
    changed: List[str] = []

    # Check if update is needed first
    update_needed, remote_version = _check_version_update_needed()
    if not update_needed:
        log_message("Sbin module is already up to date, no update needed")
        return {
            'success': True, 
            'updated': False, 
            'changed': [],
            'version': remote_version
        }

    # Backup all destinations first (only if update is needed)
    backup_targets = [(_dest_path(f)).as_posix() for f in files]
    state.backup_module_state('sbin', description='sbin files', files=backup_targets)

    # Since version check passed, we know updates are needed
    # Just copy all files and set permissions - no need for individual SHA256 checks
    for entry in files:
        source = resolve_source(entry, module_dir)
        dest = _dest_path(entry)
        if not bool(entry.get('keepUpdated', True)):
            log_message(f"Skipping (keepUpdated=false): {dest}")
            continue

        # Replace atomically
        dest.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile('wb', delete=False, dir=dest.parent) as tmp:
            shutil.copyfile(source, tmp.name)
            tmp_path = Path(tmp.name)
        
        # Set perms before swap
        perm_mgr.set_permissions([PermissionTarget(tmp_path.as_posix(), entry.get('owner','root'), entry.get('group','root'), int(entry.get('mode','755'),8))])
        os.replace(tmp_path, dest)
        changed.append(str(dest))
        log_message(f"Updated sbin: {dest}")

    # CRITICAL FIX: Update local index.json to prevent unnecessary re-runs
    if changed and remote_version:
        _update_local_version(module_dir, remote_version)

    return { 
        'success': True, 
        'updated': len(changed) > 0, 
        'changed': changed,
        'version': remote_version
    }


def main(args=None):
    module_dir = Path(__file__).parent
    
    # Module directory for reference
    
    # Now run with latest code
    if args and '--check' in args:
        return check(module_dir)
    return apply(module_dir)


