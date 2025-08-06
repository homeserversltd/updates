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
along with this program.  If not, see <https://www.gnu.org/licenses/>.

---

Updates Orchestrator System

This package provides a schema-version driven update orchestration system.
It enables live, dynamic management of service/component updates by comparing
schema versions between local modules and a GitHub repository source of truth.

Architecture:
- Git clone/pull updates repository to get latest module definitions
- Compare schema_version in each module's index.json (local vs repo)
- Clobber entire module directories when repo has newer schema_version
- Run module update scripts which handle their own configuration changes
- Each module is self-contained and version-independent

See README.md for detailed architecture and usage.
"""

import json
import importlib
import traceback
import os
import sys
import asyncio
import subprocess
import shutil
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Optional, Callable, Tuple
from pathlib import Path

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
    if not os.path.exists(index_file):
        return None
    
    try:
        with open(index_file, 'r') as f:
            return json.load(f)
    except Exception as e:
        log_message(f"Failed to load index.json from {module_path}: {e}", "ERROR")
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
    def parse_version(version_str):
        try:
            parts = version_str.split('.')
            return [int(part) for part in parts]
        except:
            return [0, 0, 0]
    
    v1_parts = parse_version(version1)
    v2_parts = parse_version(version2)
    
    # Pad to same length
    max_len = max(len(v1_parts), len(v2_parts))
    v1_parts.extend([0] * (max_len - len(v1_parts)))
    v2_parts.extend([0] * (max_len - len(v2_parts)))
    
    for i in range(max_len):
        if v1_parts[i] < v2_parts[i]:
            return -1
        elif v1_parts[i] > v2_parts[i]:
            return 1
    
    return 0

def check_multi_level_version_update(module_config: Dict[str, Any], repo_module_path: str, local_module_path: str) -> Dict[str, Any]:
    """
    Check for updates at multiple version levels (schema and content).
    
    Args:
        module_config: Module configuration from index.json
        repo_module_path: Path to repository module directory
        local_module_path: Path to local module directory
        
    Returns:
        dict: Update status with schema_update_needed, content_update_needed, and version details
    """
    result = {
        "schema_update_needed": False,
        "content_update_needed": False,
        "schema_versions": {"local": None, "repo": None},
        "content_versions": {"local": None, "repo": None},
        "update_reason": []
    }
    
    # Load local and repo module configurations
    local_config = load_module_index(local_module_path) if os.path.exists(local_module_path) else None
    repo_config = load_module_index(repo_module_path) if os.path.exists(repo_module_path) else None
    
    # Check schema version updates
    if local_config and repo_config:
        local_schema = local_config.get("metadata", {}).get("schema_version", "0.0.0")
        repo_schema = repo_config.get("metadata", {}).get("schema_version", "0.0.0")
        
        result["schema_versions"]["local"] = local_schema
        result["schema_versions"]["repo"] = repo_schema
        
        if compare_schema_versions(repo_schema, local_schema) > 0:
            result["schema_update_needed"] = True
            result["update_reason"].append(f"Schema version update: {local_schema} → {repo_schema}")
    
    # Check content version updates if configured
    version_checking = module_config.get("config", {}).get("version_checking", {})
    if version_checking.get("enabled", False):
        content_version_file = version_checking.get("content_version_file")
        content_version_path = version_checking.get("content_version_path")
        
        if content_version_file and content_version_path:
            # Get local content version
            local_content_version = None
            if local_config:
                local_content_file = os.path.join(local_module_path, content_version_file)
                if os.path.exists(local_content_file):
                    try:
                        with open(local_content_file, 'r') as f:
                            local_content = json.load(f)
                        # Navigate the JSON path (e.g., "global.version.release")
                        local_content_version = local_content
                        for key in content_version_path.split('.'):
                            if isinstance(local_content_version, dict) and key in local_content_version:
                                local_content_version = local_content_version[key]
                            else:
                                local_content_version = None
                                break
                    except Exception as e:
                        log_message(f"Failed to read local content version: {e}", "WARNING")
            
            # Get repo content version
            repo_content_version = None
            if repo_config:
                repo_content_file = os.path.join(repo_module_path, content_version_file)
                if os.path.exists(repo_content_file):
                    try:
                        with open(repo_content_file, 'r') as f:
                            repo_content = json.load(f)
                        # Navigate the JSON path
                        repo_content_version = repo_content
                        for key in content_version_path.split('.'):
                            if isinstance(repo_content_version, dict) and key in repo_content_version:
                                repo_content_version = repo_content_version[key]
                            else:
                                repo_content_version = None
                                break
                    except Exception as e:
                        log_message(f"Failed to read repo content version: {e}", "WARNING")
            
            result["content_versions"]["local"] = local_content_version
            result["content_versions"]["repo"] = repo_content_version
            
            if local_content_version and repo_content_version:
                if compare_schema_versions(repo_content_version, local_content_version) > 0:
                    result["content_update_needed"] = True
                    result["update_reason"].append(f"Content version update: {local_content_version} → {repo_content_version}")
    
    # Determine if update is needed based on configuration
    check_both = version_checking.get("check_both_versions", True)
    require_content = version_checking.get("require_content_update", False)
    
    if check_both:
        result["update_needed"] = result["schema_update_needed"] or result["content_update_needed"]
    elif require_content:
        result["update_needed"] = result["content_update_needed"]
    else:
        result["update_needed"] = result["schema_update_needed"]
    
    return result

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
    try:
        # Always remove existing directory and clone fresh to avoid ownership/permission issues
        if os.path.exists(local_path):
            log_message(f"Removing existing repository at {local_path}")
            shutil.rmtree(local_path)
        
        # Clone repository fresh
        log_message(f"Cloning repository {repo_url} (branch: {branch}) to {local_path}")
        result = subprocess.run(
            ["git", "clone", "-b", branch, repo_url, local_path],
            capture_output=True,
            text=True,
            check=True
        )
        log_message(f"Git clone completed")
        
        return True
    except subprocess.CalledProcessError as e:
        log_message(f"Git operation failed: {e.stderr}", "ERROR")
        return False
    except Exception as e:
        log_message(f"Sync failed: {e}", "ERROR")
        return False

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
    
    # Check if repo has modules subdirectory, otherwise use repo root
    repo_search_path = repo_modules_path
    if os.path.exists(os.path.join(repo_modules_path, "modules")):
        repo_search_path = os.path.join(repo_modules_path, "modules")
    
    # Check if local has modules subdirectory, otherwise use local root  
    local_search_path = local_modules_path
    if os.path.exists(os.path.join(local_modules_path, "modules")):
        local_search_path = os.path.join(local_modules_path, "modules")
    
    if not os.path.exists(repo_search_path):
        log_message(f"Repository modules path not found: {repo_search_path}", "ERROR")
        return modules_to_update
    
    # Check each module in the repository
    for module_name in os.listdir(repo_search_path):
        repo_module_path = os.path.join(repo_search_path, module_name)
        local_module_path = os.path.join(local_search_path, module_name)
        
        if not os.path.isdir(repo_module_path):
            continue
        
        # Load repository module index
        repo_index = load_module_index(repo_module_path)
        if not repo_index:
            log_message(f"No valid index.json found for repo module: {module_name}", "WARNING")
            continue
        
        # Load local module index (if exists)
        local_index = None
        if os.path.exists(local_module_path):
            local_index = load_module_index(local_module_path)
        
        # Check if local module is disabled - skip entirely if so
        if local_index and not local_index.get("metadata", {}).get("enabled", True):
            log_message(f"Module {module_name} is disabled, skipping update check")
            continue
        
        # Use multi-level version checking if configured, otherwise fall back to schema-only
        version_checking = repo_index.get("config", {}).get("version_checking", {})
        if version_checking.get("enabled", False):
            # Special handling for website module - use its own version checking
            if module_name == "website":
                try:
                    # Import and run the website module's check function
                    import importlib.util
                    import sys
                    
                    # Load the website module
                    spec = importlib.util.spec_from_file_location(
                        "website_module", 
                        os.path.join(local_module_path, "index.py")
                    )
                    if spec and spec.loader:
                        website_module = importlib.util.module_from_spec(spec)
                        sys.modules["website_module"] = website_module
                        spec.loader.exec_module(website_module)
                        
                        # Run the website module's check
                        check_result = website_module.main(["--check"])
                        
                        if check_result.get("update_available", False):
                            reasons = ", ".join(check_result.get("update_reasons", []))
                            log_message(f"Module {module_name} needs update: {reasons}")
                            modules_to_update.append(module_name)
                        else:
                            content_version = check_result.get("content_version", "unknown")
                            log_message(f"Module {module_name} is up to date: content {content_version}")
                    else:
                        log_message(f"Could not load website module for version checking", "WARNING")
                        # Fall back to schema-only checking
                        repo_schema_version = repo_index.get("metadata", {}).get("schema_version")
                        local_schema_version = "0.0.0"
                        if local_index:
                            local_schema_version = local_index.get("metadata", {}).get("schema_version", "0.0.0")
                        
                        if compare_schema_versions(repo_schema_version, local_schema_version) > 0:
                            log_message(f"Module {module_name} needs update: {local_schema_version} → {repo_schema_version}")
                            modules_to_update.append(module_name)
                        else:
                            log_message(f"Module {module_name} is up to date: {local_schema_version}")
                            
                except Exception as e:
                    log_message(f"Error checking website module updates: {e}", "WARNING")
                    # Fall back to schema-only checking
                    repo_schema_version = repo_index.get("metadata", {}).get("schema_version")
                    local_schema_version = "0.0.0"
                    if local_index:
                        local_schema_version = local_index.get("metadata", {}).get("schema_version", "0.0.0")
                    
                    if compare_schema_versions(repo_schema_version, local_schema_version) > 0:
                        log_message(f"Module {module_name} needs update: {local_schema_version} → {repo_schema_version}")
                        modules_to_update.append(module_name)
                    else:
                        log_message(f"Module {module_name} is up to date: {local_schema_version}")
            else:
                # Use enhanced multi-level version checking for other modules
                update_status = check_multi_level_version_update(repo_index, repo_module_path, local_module_path)
                
                if update_status["update_needed"]:
                    reasons = ", ".join(update_status["update_reason"])
                    log_message(f"Module {module_name} needs update: {reasons}")
                    modules_to_update.append(module_name)
                else:
                    schema_local = update_status["schema_versions"]["local"] or "0.0.0"
                    schema_repo = update_status["schema_versions"]["repo"] or "0.0.0"
                    log_message(f"Module {module_name} is up to date: schema {schema_local}, content versions match")
        else:
            # Fall back to original schema-only checking
            repo_schema_version = repo_index.get("metadata", {}).get("schema_version")
            if not repo_schema_version:
                log_message(f"No schema_version found in repo module: {module_name}", "WARNING")
                continue
            
            local_schema_version = "0.0.0"  # Default for new modules
            if local_index:
                local_schema_version = local_index.get("metadata", {}).get("schema_version", "0.0.0")
            
            # Compare versions
            if compare_schema_versions(repo_schema_version, local_schema_version) > 0:
                log_message(f"Module {module_name} needs update: {local_schema_version} → {repo_schema_version}")
                modules_to_update.append(module_name)
            else:
                log_message(f"Module {module_name} is up to date: {local_schema_version}")
    
    return modules_to_update

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
            
            # Create backup if local module exists
            if os.path.exists(local_module_path):
                backup_path = f"{local_module_path}.backup"
                if os.path.exists(backup_path):
                    shutil.rmtree(backup_path)
                shutil.move(local_module_path, backup_path)
                log_message(f"Backed up {module_name} to {backup_path}")
            
            # Copy repo module to local
            shutil.copytree(repo_module_path, local_module_path)
            log_message(f"Updated module {module_name}")
            
            # Ensure all shell scripts in the module are executable
            make_shell_scripts_executable(local_module_path)
            
            # Run the module's update script
            update_result = run_update(module_name)
            results[module_name] = update_result is not None
            
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