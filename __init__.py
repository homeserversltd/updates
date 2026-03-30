"""
HOMESERVER Update Management System
Copyright (C) 2024 HOMESERVER LLC

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.
"""

import os
import json
import shutil
import subprocess
import importlib
import traceback
import asyncio
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
from concurrent.futures import ThreadPoolExecutor
import sys
import datetime
import time

try:
    import fcntl  # Unix: serialize sync_from_repo across concurrent updaters
except ImportError:
    fcntl = None  # type: ignore

# Debug flag for verbose logging
DEBUG = False

def log_message(message: str, level: str = "INFO"):
    """Log a message with a timestamp and level to stdout."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}", file=sys.stdout)

def debug_log(message: str):
    """Debug logging that only shows when DEBUG=True."""
    if DEBUG:
        log_message(message, "DEBUG")

# Import shared utilities
from .utils.index import log_message

# Re-export utilities for easy access by submodules
__all__ = [
    'log_message', 
    'run_update', 
    'run_updates_async', 
    'load_module_index',
    'compare_schema_versions',
    'sync_from_repo',
    'detect_module_updates',
    'update_modules',
    'get_branch_from_index',
    'make_shell_scripts_executable'
]

def load_module_index(module_path: str) -> Optional[Dict[str, Any]]:
    """
    Load a module's index.json file containing metadata and configuration.
    
    Args:
        module_path: Path to the module directory
        
    Returns:
        dict: The loaded index.json data, or None if not found/invalid
    """
    index_file = os.path.join(module_path, 'index.json')
    debug_log(f"    📁 Attempting to load: {index_file}")
    
    if not os.path.exists(index_file):
        debug_log(f"    ❌ File does not exist: {index_file}")
        return None
    
    try:
        with open(index_file, 'r') as f:
            content = f.read()
            debug_log(f"    📄 File content length: {len(content)} characters")
            data = json.loads(content)
            debug_log(f"    ✅ Successfully loaded index.json from {module_path}")
            return data
    except Exception as e:
        log_message(f"    ❌ Failed to load index.json from {module_path}: {e}", "ERROR")
        return None


def compare_schema_versions(version1: str, version2: str) -> int:
    """
    Compare two semantic version strings.
    
    Args:
        version1: First version string (e.g., "1.0.0")
        version2: Second version string (e.g., "1.1.0")
        
    Returns:
        int: -1 if version1 < version2, 0 if equal, 1 if version1 > version2
    """
    debug_log(f"      🔍 Comparing versions: '{version1}' vs '{version2}'")
    
    def parse_version(version_str):
        try:
            parts = version_str.split('.')
            parsed = [int(part) for part in parts]
            debug_log(f"      📊 Parsed '{version_str}' → {parsed}")
            return parsed
        except Exception as e:
            debug_log(f"      ⚠️ Failed to parse version '{version_str}': {e}")
            return [0, 0, 0]
    
    v1_parts = parse_version(version1)
    v2_parts = parse_version(version2)
    
    # Pad to same length
    max_len = max(len(v1_parts), len(v2_parts))
    v1_parts.extend([0] * (max_len - len(v1_parts)))
    v2_parts.extend([0] * (max_len - len(v2_parts)))
    
    debug_log(f"      📏 Padded versions: {v1_parts} vs {v2_parts}")
    
    for i in range(max_len):
        if v1_parts[i] < v2_parts[i]:
            debug_log(f"      ✅ Result: {version1} < {version2} (returning -1)")
            return -1
        elif v1_parts[i] > v2_parts[i]:
            debug_log(f"      ✅ Result: {version1} > {version2} (returning +1)")
            return 1
    
    debug_log(f"      ✅ Result: {version1} = {version2} (returning 0)")
    return 0

# This function has been removed - we only need simple schema version comparison

def sync_from_repo(repo_url: str, local_path: str, branch: str = "main") -> bool:
    """
    Sync updates from a Git repository.
    
    Args:
        repo_url: URL of the Git repository
        local_path: Local path to sync to
        branch: Git branch to sync (default: main)
        
    Returns:
        bool: True if sync successful, False otherwise
    """
    lock_path = f"{local_path}.sync.lock"
    lock_fd: Optional[int] = None

    def _acquire_sync_lock() -> None:
        nonlocal lock_fd
        if fcntl is None:
            return
        try:
            lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            log_message(f"[SYNC] Acquired exclusive lock {lock_path}")
        except OSError as e:
            log_message(f"[SYNC] Could not acquire sync lock ({e}); continuing", "WARNING")
            if lock_fd is not None:
                try:
                    os.close(lock_fd)
                except OSError:
                    pass
                lock_fd = None

    def _release_sync_lock() -> None:
        nonlocal lock_fd
        if lock_fd is None or fcntl is None:
            return
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
        except OSError:
            pass
        lock_fd = None

    def _unlink_stale_git_config_lock(path: str) -> None:
        lock_file = os.path.join(path, ".git", "config.lock")
        if os.path.isfile(lock_file):
            try:
                os.unlink(lock_file)
                log_message(f"[SYNC] Removed stale git lock {lock_file}")
            except OSError as e:
                log_message(f"[SYNC] Could not remove stale lock {lock_file}: {e}", "WARNING")

    def _safe_rmtree(path: str) -> None:
        """
        Remove directory tree while tolerating transient ENOENT races.

        Git can mutate .git internals while another update process is cleaning
        the same temp directory; missing entries during traversal should not
        abort sync when the end goal is "path removed before fresh clone".
        """
        def _onerror(_func, _target_path, exc_info):
            exc = exc_info[1]
            if isinstance(exc, FileNotFoundError):
                return
            raise exc

        shutil.rmtree(path, onerror=_onerror)

    def _force_remove_repo_path(path: str) -> None:
        """If Python rmtree leaves debris (permissions, races), use rm -rf once."""
        if not os.path.exists(path):
            return
        _unlink_stale_git_config_lock(path)
        try:
            result = subprocess.run(
                ["/bin/rm", "-rf", path],
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                timeout=120,
            )
            if result.returncode != 0:
                log_message(
                    f"[SYNC] /bin/rm -rf exit {result.returncode}: {result.stderr or result.stdout}",
                    "WARNING",
                )
        except subprocess.TimeoutExpired:
            log_message(f"[SYNC] Timeout removing {path}", "WARNING")
        except Exception as e:
            log_message(f"[SYNC] Force remove failed: {e}", "WARNING")

    def _prepare_empty_clone_target() -> None:
        """Ensure local_path does not exist before git clone (avoids config.lock races)."""
        if not os.path.exists(local_path):
            return
        log_message(f"Removing existing repository at {local_path}")
        _unlink_stale_git_config_lock(local_path)
        try:
            _safe_rmtree(local_path)
        except FileNotFoundError:
            log_message(f"[SYNC] Repository path vanished during cleanup: {local_path}")
        if os.path.exists(local_path):
            log_message(
                f"[SYNC] Path still present after rmtree; forcing removal: {local_path}",
                "WARNING",
            )
            _force_remove_repo_path(local_path)

    try:
        _acquire_sync_lock()

        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        clone_cmd = ["git", "clone", "-b", branch, repo_url, local_path]

        for attempt in range(2):
            _prepare_empty_clone_target()
            if attempt > 0:
                time.sleep(0.5)
            log_message(
                f"[SYNC] Cloning repository {repo_url} (branch: {branch}) to {local_path}"
                + ("" if attempt == 0 else " (retry after cleanup)")
            )
            result = subprocess.run(
                clone_cmd,
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                env=env,
            )
            if result.returncode == 0:
                log_message("[SYNC] Git clone completed successfully")
                return True

            err = (result.stderr or "") + (result.stdout or "")
            log_message(f"Git clone failed (attempt {attempt + 1}): {err}", "ERROR")
            if attempt == 1:
                return False
            log_message("[SYNC] Retrying once after full cleanup", "WARNING")

    except Exception as e:
        log_message(f"Sync failed: {e}", "ERROR")
        return False
    finally:
        _release_sync_lock()

def get_branch_from_index(index_data: dict) -> str:
    """
    Extract branch configuration from index.json data.
    
    Args:
        index_data: Loaded index.json data
        
    Returns:
        str: Branch name, defaults to "master" if not specified
    """
    if not index_data:
        return "master"
    
    return index_data.get("metadata", {}).get("branch", "master")

def make_shell_scripts_executable(directory_path: str) -> None:
    """
    Recursively make all .sh files in a directory executable.
    
    This function ensures that shell scripts maintain executable permissions
    after being copied from repositories, which may not preserve execute bits
    depending on the source repository's permissions and the copy method used.
    
    Args:
        directory_path: Path to directory to process (absolute path recommended)
        
    Note:
        - Uses relative paths in log messages for readability
        - Sets execute permissions for user, group, and other (755-style)
        - Handles permission errors gracefully with warnings
    """
    import stat
    
    for root, dirs, files in os.walk(directory_path):
        for file in files:
            if file.endswith('.sh'):
                file_path = os.path.join(root, file)
                try:
                    current_permissions = os.stat(file_path).st_mode
                    os.chmod(file_path, current_permissions | stat.S_IEXEC | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                    log_message(f"Made executable: {os.path.relpath(file_path, directory_path)}")
                except Exception as e:
                    log_message(f"Failed to make executable {file_path}: {e}", "WARNING")

def detect_module_updates(local_modules_path: str, repo_modules_path: str) -> List[str]:
    """
    Detect which modules need updates by comparing schema versions and content versions.
    
    Args:
        local_modules_path: Path to local modules directory
        repo_modules_path: Path to repository modules directory
        
    Returns:
        List[str]: List of module names that need updates
    """
    modules_to_update = []
    
    debug_log(f"🔍 Starting module update detection...")
    debug_log(f"  Local modules path: {local_modules_path}")
    debug_log(f"  Repository modules path: {repo_modules_path}")
    
    # Check if repo has modules subdirectory, otherwise use repo root
    repo_search_path = repo_modules_path
    if os.path.exists(os.path.join(repo_modules_path, "modules")):
        repo_search_path = os.path.join(repo_modules_path, "modules")
        debug_log(f"  Using repository modules subdirectory: {repo_search_path}")
    else:
        debug_log(f"  Using repository root as modules path: {repo_search_path}")
    
    # Check if local has modules subdirectory, otherwise use local root  
    local_search_path = local_modules_path
    if os.path.exists(os.path.join(local_modules_path, "modules")):
        local_search_path = os.path.join(local_modules_path, "modules")
        debug_log(f"  Using local modules subdirectory: {local_search_path}")
    else:
        debug_log(f"  Using local root as modules path: {local_search_path}")
    
    if not os.path.exists(repo_search_path):
        log_message(f"❌ Repository modules path not found: {repo_search_path}", "ERROR")
        return modules_to_update
    
    # Check each module in the repository
    repo_modules = os.listdir(repo_search_path)
    debug_log(f"📦 Found {len(repo_modules)} modules in repository: {', '.join(repo_modules)}")
    
    for module_name in repo_modules:
        repo_module_path = os.path.join(repo_search_path, module_name)
        local_module_path = os.path.join(local_search_path, module_name)
        
        debug_log(f"🔍 Checking module: {module_name}")
        debug_log(f"  Repository path: {repo_module_path}")
        debug_log(f"  Local path: {local_module_path}")
        
        if not os.path.isdir(repo_module_path):
            debug_log(f"  ⏭️ Skipping {module_name} - not a directory")
            continue
        
        # Load repository module index
        debug_log(f"  📖 Loading repository index.json...")
        repo_index = load_module_index(repo_module_path)
        if not repo_index:
            log_message(f"  ❌ No valid index.json found for repo module: {module_name}", "WARNING")
            continue
        
        repo_schema_version = repo_index.get("metadata", {}).get("schema_version", "unknown")
        debug_log(f"  📋 Repository schema version: {repo_schema_version}")
        
        # Load local module index (if exists)
        local_index = None
        if os.path.exists(local_module_path):
            debug_log(f"  📖 Loading local index.json...")
            local_index = load_module_index(local_module_path)
            if local_index:
                local_schema_version = local_index.get("metadata", {}).get("schema_version", "unknown")
                debug_log(f"  📋 Local schema version: {local_schema_version}")
            else:
                debug_log(f"  ⚠️ Failed to load local index.json")
        else:
            debug_log(f"  📁 Local module directory does not exist")
        
        # Check if local module is disabled - skip entirely if so
        if local_index and not local_index.get("metadata", {}).get("enabled", True):
            debug_log(f"  ⏭️ Module {module_name} is disabled, skipping update check")
            continue
        
        # Simple schema version comparison - no special cases, no module self-evaluation
        repo_schema_version = repo_index.get("metadata", {}).get("schema_version")
        if not repo_schema_version:
            log_message(f"  ❌ No schema_version found in repo module: {module_name}", "WARNING")
            continue
        
        local_schema_version = "0.0.0"  # Default for new modules
        if local_index:
            local_schema_version = local_index.get("metadata", {}).get("schema_version", "0.0.0")
        
        debug_log(f"  📊 Schema version comparison: {local_schema_version} vs {repo_schema_version}")
        comparison = compare_schema_versions(repo_schema_version, local_schema_version)
        debug_log(f"  🔍 Comparison result: {comparison} (0=equal, >0=repo_newer, <0=local_newer)")
        
        # Compare versions - if repo is newer, update is needed
        if comparison > 0:
            log_message(f"  ✅ Module {module_name} needs update: {local_schema_version} → {repo_schema_version}")
            modules_to_update.append(module_name)
        else:
            debug_log(f"  ✅ Module {module_name} is up to date: {local_schema_version}")
        
        debug_log(f"  {'='*50}")
    
    debug_log(f"🎯 Module detection complete. Found {len(modules_to_update)} modules needing updates: {modules_to_update}")
    return modules_to_update


def _preserve_local_repository_config(backup_module_path: str, local_module_path: str, module_name: str) -> None:
    """
    After a schema update (copytree from repo), restore the local module's repository
    dict (repo or config.repository) into the new index.json so user-configured url,
    branch, and default_branch are never clobbered by the repo version.
    """
    backup_index = os.path.join(backup_module_path, "index.json")
    local_index_path = os.path.join(local_module_path, "index.json")
    if not os.path.exists(backup_index) or not os.path.exists(local_index_path):
        return
    try:
        with open(backup_index, "r") as f:
            backup_data = json.load(f)
        with open(local_index_path, "r") as f:
            local_data = json.load(f)
        preserved = False
        if "repo" in backup_data and isinstance(backup_data["repo"], dict):
            local_data["repo"] = backup_data["repo"].copy()
            preserved = True
            log_message(f"Preserved repo config (url, branch, default_branch) for {module_name}")
        if "config" in backup_data and isinstance(backup_data["config"], dict):
            repo_config = backup_data["config"].get("repository")
            if isinstance(repo_config, dict):
                if "config" not in local_data:
                    local_data["config"] = {}
                local_data["config"]["repository"] = repo_config.copy()
                preserved = True
                log_message(f"Preserved config.repository (url, branch, default_branch) for {module_name}")
        if preserved:
            with open(local_index_path, "w") as f:
                json.dump(local_data, f, indent=4)
    except Exception as e:
        log_message(f"Could not preserve repository config for {module_name}: {e}", "WARNING")


def _preserve_migrations_has_run_state(backup_module_path: str, local_module_path: str, module_name: str) -> None:
    """
    After a schema update, merge migration completion flags from the backup
    module into the new index.json by migration id.

    The shipped repo index.json lists has_run: false for all entries; without
    this merge, a module schema bump wipes months of on-disk migration state
    and forces 00000002..00000006 to run again.
    """
    if module_name != "migrations":
        return
    backup_index = os.path.join(backup_module_path, "index.json")
    local_index_path = os.path.join(local_module_path, "index.json")
    if not os.path.exists(backup_index) or not os.path.exists(local_index_path):
        return
    try:
        with open(backup_index, "r") as f:
            backup_data = json.load(f)
        with open(local_index_path, "r") as f:
            local_data = json.load(f)
        backup_migrations = backup_data.get("migrations")
        local_migrations = local_data.get("migrations")
        if not isinstance(backup_migrations, list) or not isinstance(local_migrations, list):
            return
        by_id = {
            m.get("id"): m
            for m in backup_migrations
            if isinstance(m, dict) and m.get("id")
        }
        merged = 0
        for m in local_migrations:
            if not isinstance(m, dict):
                continue
            mid = m.get("id")
            if mid in by_id and by_id[mid].get("has_run") is True:
                m["has_run"] = True
                merged += 1
        if merged:
            with open(local_index_path, "w") as f:
                json.dump(local_data, f, indent=2)
            log_message(
                f"Preserved has_run for {merged} migration(s) from backup (migrations module)"
            )
    except Exception as e:
        log_message(f"Could not preserve migrations has_run state: {e}", "WARNING")


def update_modules(modules_to_update: List[str], local_modules_path: str, repo_modules_path: str) -> Dict[str, bool]:
    """
    Update specified modules by clobbering local versions with repo versions.
    
    Args:
        modules_to_update: List of module names to update
        local_modules_path: Path to local modules directory
        repo_modules_path: Path to repository modules directory
        
    Returns:
        Dict[str, bool]: Results of each module update (module_name -> success)
    """
    results = {}
    
    # Determine search paths (same logic as detect_module_updates)
    repo_search_path = repo_modules_path
    if os.path.exists(os.path.join(repo_modules_path, "modules")):
        repo_search_path = os.path.join(repo_modules_path, "modules")
    
    local_search_path = local_modules_path
    if os.path.exists(os.path.join(local_modules_path, "modules")):
        local_search_path = os.path.join(local_modules_path, "modules")
    
    for module_name in modules_to_update:
        try:
            repo_module_path = os.path.join(repo_search_path, module_name)
            local_module_path = os.path.join(local_search_path, module_name)
            backup_path = f"{local_module_path}.backup"
            # Create backup if local module exists
            if os.path.exists(local_module_path):
                if os.path.exists(backup_path):
                    shutil.rmtree(backup_path)
                shutil.move(local_module_path, backup_path)
                log_message(f"Backed up {module_name} to {backup_path}")
            
            # Copy repo module to local
            shutil.copytree(repo_module_path, local_module_path)
            log_message(f"Updated module {module_name}")
            # Restore local repository dict (url, branch, default_branch) so schema update never clobbers it
            if os.path.exists(backup_path):
                _preserve_local_repository_config(backup_path, local_module_path, module_name)
                _preserve_migrations_has_run_state(backup_path, local_module_path, module_name)
            # Ensure all shell scripts in the module are executable
            make_shell_scripts_executable(local_module_path)
            # Schema update successful - module will be executed later in the process
            results[module_name] = True
            
        except Exception as e:
            log_message(f"Failed to update module {module_name}: {e}", "ERROR")
            results[module_name] = False
            
            # Restore backup if update failed
            backup_path = f"{local_module_path}.backup"
            if os.path.exists(backup_path):
                if os.path.exists(local_module_path):
                    shutil.rmtree(local_module_path)
                shutil.move(backup_path, local_module_path)
                log_message(f"Restored backup for {module_name}")
                
                # Ensure shell scripts in restored module are executable
                make_shell_scripts_executable(local_module_path)
    
    return results

def run_update(module_path, args=None, callback=None):
    """
    Run a single update module.
    
    Args:
        module_path (str): Import path to the module or module name
        args (list, optional): Arguments to pass to the module's main function
        callback (callable, optional): Function to call when update completes
        
    Returns:
        Any: Result from the update function
    """
    result = None
    try:
        # Handle both full import paths and simple module names
        if "." not in module_path:
            # Simple module name - look in modules subdirectory
            module_path = f"modules.{module_path}"
        
        # Use relative import from current package
        mod = importlib.import_module(f".{module_path}", package=__name__)
        if hasattr(mod, 'main'):
            log_message(f"Running update: {module_path}")
            result = mod.main(args)
            log_message(f"Completed update: {module_path}")
        else:
            log_message(f"Module {module_path} has no main(args) function.", "ERROR")
    except Exception as e:
        log_message(f"Error running update for {module_path}: {e}", "ERROR")
        traceback.print_exc()
    
    if callback and callable(callback):
        callback(module_path, result)
    
    return result

async def run_updates_async(updates, max_workers=None):
    """
    Run multiple updates asynchronously using a thread pool.
    
    Args:
        updates (list): List of dicts with 'module_path' and 'args' keys
        max_workers (int, optional): Maximum number of concurrent workers
        
    Returns:
        dict: Mapping of module paths to their results
    """
    results = {}
    
    def update_callback(module_path, result):
        results[module_path] = result
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        loop = asyncio.get_event_loop()
        futures = []
        
        for update in updates:
            module_path = update.get('module_path')
            args = update.get('args', [])
            future = loop.run_in_executor(
                executor,
                lambda mp=module_path, a=args: run_update(mp, a, update_callback)
            )
            futures.append(future)
        
        await asyncio.gather(*futures)
    
    return results


# Initialize package-level variables
manifest = None 