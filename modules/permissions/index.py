#!/usr/bin/env python3
"""
permissions Module - Manage /etc/sudoers.d flask-* files
"""
import os
import re
import json
import hashlib
import shutil
import subprocess
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


def resolve_source(p: Dict[str, Any], module_dir: Path) -> Path:
    cfg = load_config(module_dir)
    repo_dir = ensure_repo_checkout(module_dir, cfg.get('repo', {}))
    candidate = repo_dir / p['source']
    if candidate.exists():
        return candidate
    return module_dir / 'src' / p['source']


def current_permissions(path: Path) -> Dict[str, Any]:
    return get_permissions(path.as_posix())


def visudo_check(path: Path) -> bool:
    try:
        # Validate the individual file and the whole config where possible
        r1 = subprocess.run(['visudo', '-cf', str(path)], capture_output=True, text=True)
        if r1.returncode != 0:
            log_message(f"visudo validation failed for {path}: {r1.stderr}", 'ERROR')
            return False
        return True
    except Exception as e:
        log_message(f"visudo check error: {e}", 'ERROR')
        return False


def _effective_policies(module_dir: Path, cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Discover policies strictly by pattern;"""
    pattern = cfg.get('policyPattern')
    discovered: List[Dict[str, Any]] = []
    if not pattern:
        return discovered
    try:
        regex = re.compile(pattern)
        repo_dir = ensure_repo_checkout(module_dir, cfg.get('repo', {}))
        for item in repo_dir.iterdir():
            if not item.is_file():
                continue
            name = item.name
            if not regex.match(name):
                continue
            discovered.append({
                'name': name,
                'source': name,
                'destination': f"/etc/sudoers.d/{name}",
                'owner': 'root',
                'group': 'root',
                'mode': '440',
                'sha256': ''
            })
    except Exception as e:
        log_message(f"Policy discovery failed: {e}", 'WARNING')

    return discovered


def check(module_dir: Path) -> Dict[str, Any]:
    cfg = load_config(module_dir)
    policies = _effective_policies(module_dir, cfg)
    drift: List[Dict[str, Any]] = []
    state_out = { 'policies': [] }

    for p in policies:
        src = resolve_source(p, module_dir)
        dest = Path(p['destination'])
        sha_remote = sha256(src)
        sha_dest = sha256(dest)
        mode_expected = int(p.get('mode', '440'), 8)
        perm_mismatch = False
        try:
            st = os.stat(dest)
            perm_mismatch = (st.st_mode & 0o777) != mode_expected
        except FileNotFoundError:
            perm_mismatch = True

        drift.append({
            'destination': str(dest),
            'exists': dest.exists(),
            'content_match': sha_remote == sha_dest,
            'sha_remote': sha_remote,
            'sha_dest': sha_dest,
            'perm_match': not perm_mismatch
        })
        state_out['policies'].append({
            'destination': str(dest),
            'source': p.get('source'),
            'sha_remote': sha_remote,
            'sha_dest': sha_dest
        })

    # Optionally scan for unknown flask-* files
    pattern = cfg.get('policyPattern')
    unknown: List[str] = []
    if pattern:
        regex = re.compile(pattern)
        sudo_dir = Path('/etc/sudoers.d')
        if sudo_dir.exists():
            for f in sudo_dir.iterdir():
                if f.is_file() and regex.match(f.name):
                    if not any(Path(p['destination']).name == f.name for p in policies):
                        unknown.append(f.name)

    # persist state into module dir
    try:
        with (module_dir / 'manifest.state.json').open('w') as f:
            json.dump({ 'drift': drift, 'unknown': unknown, **state_out }, f, indent=2)
    except Exception as e:
        log_message(f"Failed to write permissions state: {e}", 'WARNING')

    return { 'success': True, 'updated': False, 'drift': drift, 'unknown': unknown }


def apply(module_dir: Path) -> Dict[str, Any]:
    cfg = load_config(module_dir)
    policies = _effective_policies(module_dir, cfg)
    state = StateManager('/var/backups/updates')
    perm_mgr = PermissionManager('permissions')
    changed: List[str] = []

    # Backup all targets first
    backup_targets = [p['destination'] for p in policies]
    state.backup_module_state('permissions', description='sudoers policies', files=backup_targets)

    for p in policies:
        src = resolve_source(p, module_dir)
        dest = Path(p['destination'])
        expected = p.get('sha256') or sha256(src)
        current = sha256(dest)
        needs_replace = (expected != current) or (not dest.exists())

        if not needs_replace:
            # Only correct perms if they differ
            desired_owner = p.get('owner','root')
            desired_group = p.get('group','root')
            desired_mode = int(p.get('mode','440'),8)
            cur = current_permissions(dest)
            if cur.get('owner') != desired_owner or cur.get('group') != desired_group or cur.get('mode') != desired_mode:
                perm_mgr.set_permissions([PermissionTarget(dest.as_posix(), desired_owner, desired_group, desired_mode)])
            continue

        dest.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile('wb', delete=False, dir=dest.parent) as tmp:
            shutil.copyfile(src, tmp.name)
            tmp_path = Path(tmp.name)

        # validate the temp file
        if not visudo_check(tmp_path):
            # cleanup and abort this file
            try:
                tmp_path.unlink(missing_ok=True)  # type: ignore[arg-type]
            except Exception:
                pass
            return { 'success': False, 'updated': False, 'error': f'visudo validation failed for {dest}' }

        # set perms on temp and swap
        perm_mgr.set_permissions([PermissionTarget(tmp_path.as_posix(), p.get('owner','root'), p.get('group','root'), int(p.get('mode','440'),8))])
        os.replace(tmp_path, dest)
        changed.append(str(dest))
        log_message(f"Updated sudoers policy: {dest}")

    # final full sudoers validation
    subprocess.run(['visudo', '-cf', '/etc/sudoers'], check=False)

    return { 'success': True, 'updated': len(changed) > 0, 'changed': changed }


def main(args=None):
    module_dir = Path(__file__).parent
    
    # Module directory for reference
    
    # Now run with latest code
    if args and '--check' in args:
        return check(module_dir)
    return apply(module_dir)


