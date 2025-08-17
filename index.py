#!/usr/bin/env python3
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
"""

import asyncio
import json
import os
import sys
import argparse
import logging
import subprocess
from pathlib import Path
from datetime import datetime
from . import compare_schema_versions, run_update, load_module_index, sync_from_repo, detect_module_updates, update_modules

# Add current directory to path for relative imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def setup_global_update_logging():
    """
    Log to stdout only; the shell wrapper owns file truncation/redirection.
    """
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    unified_format = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s',
                                       datefmt='%Y-%m-%d %H:%M:%S')
    console_handler.setFormatter(unified_format)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    for h in list(root_logger.handlers):
        root_logger.removeHandler(h)
    root_logger.addHandler(console_handler)
    logging.info("="*80)
    logging.info("HOMESERVER UPDATE SESSION STARTED")
    logging.info(f"Command: {' '.join(sys.argv)}")
    logging.info(f"Working Directory: {os.getcwd()}")
    logging.info(f"Python Version: {sys.version}")
    logging.info("="*80)

def log_message(message: str, level: str = "INFO"):
    """Unified logger used throughout the orchestrator and helpers."""
    if level == "ERROR":
        logging.error(message)
    elif level == "WARNING":
        logging.warning(message)
    else:
        logging.info(message)

def log_to_file(message: str, level: str = "INFO"):
    # Alias to stdout logging; file persistence handled by shell wrapper
    if level == "ERROR":
        logging.error(message)
    elif level == "WARNING":
        logging.warning(message)
    else:
        logging.info(message)

# Configuration
DEFAULT_REPO_URL = "https://github.com/homeserversltd/updates.git"
DEFAULT_LOCAL_PATH = "/tmp/homeserver-updates-repo"
DEFAULT_MODULES_PATH = "/usr/local/lib/updates"

def load_global_index(modules_path: str) -> dict:
    """Load the global index.json that tracks current module versions."""
    index_file = os.path.join(modules_path, "index.json")
    if os.path.exists(index_file):
        try:
            with open(index_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            log_message(f"Failed to load global index.json: {e}", "ERROR")
    
    # Return default structure if not found
    return {
        "metadata": {
            "schema_version": "1.0.0",
            "channel": "stable",
            "branch": "master"
        },
        "packages": {}
    }

def update_global_index(modules_path: str, updated_modules: list, orchestrator_updated: bool = False, repo_modules_path: str = None) -> bool:
    """Update the global index.json with new module versions and orchestrator schema version."""
    try:
        index_file = os.path.join(modules_path, "index.json")
        global_index = load_global_index(modules_path)
        
        # Update package versions based on updated modules
        for module_name in updated_modules:
            schema_version = "1.0.0"  # Default fallback
            
            # First try to get schema version from repository (what we actually deployed)
            if repo_modules_path:
                repo_search_path = repo_modules_path
                if os.path.exists(os.path.join(repo_modules_path, "modules")):
                    repo_search_path = os.path.join(repo_modules_path, "modules")
                
                repo_module_path = os.path.join(repo_search_path, module_name)
                if os.path.exists(repo_module_path):
                    repo_module_index = load_module_index(repo_module_path)
                    if repo_module_index:
                        schema_version = repo_module_index.get("metadata", {}).get("schema_version", "1.0.0")
                        log_message(f"Updated global index: {module_name} → {schema_version} (from repository)")
                        global_index["packages"][module_name] = schema_version
                        continue
            
            # Fallback: get schema version from local module (what we actually have)
            local_module_path = os.path.join(modules_path, "modules", module_name)
            if not os.path.exists(local_module_path):
                local_module_path = os.path.join(modules_path, module_name)
            
            module_index = load_module_index(local_module_path)
            if module_index:
                schema_version = module_index.get("metadata", {}).get("schema_version", "1.0.0")
                log_message(f"Updated global index: {module_name} → {schema_version} (from local)")
            
            global_index["packages"][module_name] = schema_version
        
        # Update orchestrator schema version if it was updated
        if orchestrator_updated:
            # Get new orchestrator schema version from repo
            repo_index_path = os.path.join(DEFAULT_LOCAL_PATH, "index.json")
            if os.path.exists(repo_index_path):
                with open(repo_index_path, 'r') as f:
                    repo_index = json.load(f)
                new_schema_version = repo_index.get("metadata", {}).get("schema_version", "1.0.0")
                global_index["metadata"]["schema_version"] = new_schema_version
                log_message(f"Updated orchestrator schema version: {new_schema_version}")
        
        # Write updated index
        with open(index_file, 'w') as f:
            json.dump(global_index, f, indent=4)
        
        log_message(f"Global index updated with {len(updated_modules)} modules" + 
                   (" and orchestrator" if orchestrator_updated else ""))
        return True
        
    except Exception as e:
        log_message(f"Failed to update global index: {e}", "ERROR")
        return False

def update_homeserver_config_timestamp() -> bool:
    """
    Update the lastUpdated timestamp in the homeserver config file.
    This ensures the frontend shows accurate "Last Updated" information.
    """
    try:
        
        homeserver_config_path = "/var/www/homeserver/src/config/homeserver.json"
        
        if not os.path.exists(homeserver_config_path):
            log_message(f"Homeserver config not found at {homeserver_config_path}", "WARNING")
            return False
        
        # Read current config
        with open(homeserver_config_path, 'r') as f:
            config_data = json.load(f)
        
        # Update the lastUpdated timestamp
        current_date = datetime.now().strftime("%m-%d-%Y")
        
        # Ensure the global.version structure exists
        if "global" not in config_data:
            config_data["global"] = {}
        if "version" not in config_data["global"]:
            config_data["global"]["version"] = {}
        
        config_data["global"]["version"]["lastUpdated"] = current_date
        
        # Write updated config
        with open(homeserver_config_path, 'w') as f:
            json.dump(config_data, f, indent=4)
        
        log_message(f"Updated homeserver config lastUpdated to: {current_date}")
        return True
        
    except Exception as e:
        log_message(f"Failed to update homeserver config timestamp: {e}", "ERROR")
        return False

def check_orchestrator_update(modules_path: str, repo_path: str) -> bool:
    """Check if the orchestrator system needs updating by comparing schema versions."""
    try:
        # Load local orchestrator schema version
        local_index_path = os.path.join(modules_path, "index.json")
        local_schema_version = "0.0.0"  # Default for missing version
        
        if os.path.exists(local_index_path):
            with open(local_index_path, 'r') as f:
                local_index = json.load(f)
            local_schema_version = local_index.get("metadata", {}).get("schema_version", "0.0.0")
        
        # Load repository orchestrator schema version
        repo_index_path = os.path.join(repo_path, "index.json")
        if not os.path.exists(repo_index_path):
            log_message("No orchestrator schema version found in repository", "WARNING")
            return False
        
        with open(repo_index_path, 'r') as f:
            repo_index = json.load(f)
        repo_schema_version = repo_index.get("metadata", {}).get("schema_version", "0.0.0")
        
        # Compare versions using existing function
        needs_update = compare_schema_versions(repo_schema_version, local_schema_version) > 0
        
        if needs_update:
            log_message(f"Orchestrator needs update: {local_schema_version} → {repo_schema_version}")
        else:
            log_message(f"Orchestrator is up to date: {local_schema_version}")
        
        return needs_update
        
    except Exception as e:
        log_message(f"Failed to check orchestrator version: {e}", "ERROR")
        return False

def update_orchestrator(modules_path: str, repo_path: str) -> bool:
    """
    Update the orchestrator system files from repository.
    
    This function preserves user-configured branch and channel preferences
    when updating the orchestrator's index.json file. This ensures that
    users who manually set a specific branch (e.g., 'develop', 'test')
    will maintain their preference even after orchestrator updates.
    """
    try:
        import shutil
        import tempfile
        
        # Files to update in the orchestrator
        orchestrator_files = [
            "index.py",
            "updateManager.sh", 
            "setup_venv.sh",
            "__init__.py",
            "utils/",
            "requirements.txt"
        ]
        
        # Create backup directory
        backup_dir = os.path.join(modules_path, ".orchestrator_backup")
        if os.path.exists(backup_dir):
            shutil.rmtree(backup_dir)
        os.makedirs(backup_dir)
        
        log_message("Creating orchestrator backup...")
        
        # Backup existing files
        for file_name in orchestrator_files:
            local_path = os.path.join(modules_path, file_name)
            backup_path = os.path.join(backup_dir, file_name)
            
            if os.path.exists(local_path):
                if os.path.isdir(local_path):
                    shutil.copytree(local_path, backup_path)
                else:
                    os.makedirs(os.path.dirname(backup_path), exist_ok=True)
                    shutil.copy2(local_path, backup_path)
                log_message(f"Backed up: {file_name}")
        
        log_message("Updating orchestrator files...")
        
        # Update files from repository
        for file_name in orchestrator_files:
            repo_file_path = os.path.join(repo_path, file_name)
            local_file_path = os.path.join(modules_path, file_name)
            
            if os.path.exists(repo_file_path):
                # Remove existing file/directory
                if os.path.exists(local_file_path):
                    if os.path.isdir(local_file_path):
                        shutil.rmtree(local_file_path)
                    else:
                        os.remove(local_file_path)
                
                # Copy new version
                if os.path.isdir(repo_file_path):
                    shutil.copytree(repo_file_path, local_file_path)
                else:
                    os.makedirs(os.path.dirname(local_file_path), exist_ok=True)
                    shutil.copy2(repo_file_path, local_file_path)
                
                # Ensure shell scripts are executable
                if file_name.endswith('.sh'):
                    import stat
                    current_permissions = os.stat(local_file_path).st_mode
                    os.chmod(local_file_path, current_permissions | stat.S_IEXEC | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                    log_message(f"Made executable: {file_name}")
                
                log_message(f"Updated: {file_name}")
            else:
                log_message(f"File not found in repository: {file_name}", "WARNING")
        
        # Update the index.json with new orchestrator version while preserving user branch preference
        repo_index_path = os.path.join(repo_path, "index.json")
        local_index_path = os.path.join(modules_path, "index.json")
        
        if os.path.exists(repo_index_path):
            # Preserve user's branch preference from local index
            user_branch = None
            user_channel = None
            if os.path.exists(local_index_path):
                try:
                    with open(local_index_path, 'r') as f:
                        local_index = json.load(f)
                    user_branch = local_index.get("metadata", {}).get("branch")
                    user_channel = local_index.get("metadata", {}).get("channel")
                    log_message(f"Preserving user branch preference: {user_branch}")
                except Exception as e:
                    log_message(f"Warning: Could not read local index for branch preservation: {e}", "WARNING")
            
            # Load repository index and update with preserved user preferences
            with open(repo_index_path, 'r') as f:
                repo_index = json.load(f)
            
            # Preserve user's branch and channel preferences if they exist
            if user_branch is not None:
                repo_index["metadata"]["branch"] = user_branch
                log_message(f"Preserved user branch: {user_branch}")
            if user_channel is not None:
                repo_index["metadata"]["channel"] = user_channel
                log_message(f"Preserved user channel: {user_channel}")
            
            # Write the merged index with preserved user preferences
            with open(local_index_path, 'w') as f:
                json.dump(repo_index, f, indent=4)
            
            log_message("Updated: index.json (with preserved user preferences)")
        
        log_message("Orchestrator update completed successfully")
        return True
        
    except Exception as e:
        log_message(f"Failed to update orchestrator: {e}", "ERROR")
        
        # Attempt to restore from backup
        try:
            log_message("Attempting to restore orchestrator from backup...")
            backup_dir = os.path.join(modules_path, ".orchestrator_backup")
            
            if os.path.exists(backup_dir):
                for file_name in orchestrator_files:
                    backup_path = os.path.join(backup_dir, file_name)
                    local_path = os.path.join(modules_path, file_name)
                    
                    if os.path.exists(backup_path):
                        if os.path.exists(local_path):
                            if os.path.isdir(local_path):
                                shutil.rmtree(local_path)
                            else:
                                os.remove(local_path)
                        
                        if os.path.isdir(backup_path):
                            shutil.copytree(backup_path, local_path)
                        else:
                            shutil.copy2(backup_path, local_path)
                            
                            # Ensure shell scripts are executable after restore
                            if file_name.endswith('.sh'):
                                import stat
                                current_permissions = os.stat(local_path).st_mode
                                os.chmod(local_path, current_permissions | stat.S_IEXEC | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                
                log_message("Orchestrator restored from backup")
            
        except Exception as restore_error:
            log_message(f"Failed to restore orchestrator backup: {restore_error}", "ERROR")
        
        return False

def get_enabled_modules(modules_path: str) -> list:
    """Get list of all enabled modules that should be executed."""
    enabled_modules = []
    
    try:
        # Check both possible module locations
        modules_search_path = os.path.join(modules_path, "modules")
        if not os.path.exists(modules_search_path):
            modules_search_path = modules_path
        
        if not os.path.exists(modules_search_path):
            log_message("No modules directory found", "WARNING")
            return enabled_modules
        
        for item in os.listdir(modules_search_path):
            item_path = os.path.join(modules_search_path, item)
            if os.path.isdir(item_path):
                # Skip backup directories created by StateManager
                if item.endswith('.backup'):
                    log_message(f"Skipping backup directory: {item}")
                    continue
                
                index_file = os.path.join(item_path, "index.json")
                if os.path.exists(index_file):
                    try:
                        with open(index_file, 'r') as f:
                            config = json.load(f)
                        
                        # Check if module is enabled (default to True if not specified)
                        enabled = config.get("metadata", {}).get("enabled", True)
                        if enabled:
                            enabled_modules.append(item)
                            log_message(f"Found enabled module: {item}")
                        else:
                            log_message(f"Skipping disabled module: {item}")
                    except Exception as e:
                        log_message(f"Error reading module '{item}': {e}", "WARNING")
        
        log_message(f"Total enabled modules: {len(enabled_modules)}")
        return enabled_modules
        
    except Exception as e:
        log_message(f"Failed to get enabled modules: {e}", "ERROR")
        return enabled_modules

def run_update_with_logging(module_path: str, args=None):
    """
    Enhanced version of run_update that captures and logs all subprocess output.
    This ensures ALL module output gets streamed to the centralized log file.
    """
    try:
        # Import the module dynamically
        module_parts = module_path.split('.')
        module = __import__(module_path, fromlist=[module_parts[-1]])
        
        # Check if module has a main function
        if hasattr(module, 'main'):
            log_to_file(f"Calling {module_path}.main() with output capture...")
            
            # Capture the module's output by temporarily redirecting stdout/stderr
            import io
            import contextlib
            
            # Create string buffers to capture output
            stdout_buffer = io.StringIO()
            stderr_buffer = io.StringIO()
            
            # Redirect stdout and stderr to our buffers
            with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(stderr_buffer):
                try:
                    result = module.main(args)
                except Exception as module_error:
                    log_to_file(f"Module {module_path} raised exception: {module_error}", "ERROR")
                    result = {"success": False, "error": str(module_error)}
            
            # Get captured output
            stdout_content = stdout_buffer.getvalue()
            stderr_content = stderr_buffer.getvalue()
            
            # Log captured output to our centralized log
            if stdout_content.strip():
                log_to_file("STDOUT from module:")
                for line in stdout_content.strip().split('\n'):
                    log_to_file(f"  {line}")
            
            if stderr_content.strip():
                log_to_file("STDERR from module:", "WARNING")
                for line in stderr_content.strip().split('\n'):
                    log_to_file(f"  {line}", "WARNING")
            
            log_to_file(f"Module {module_path} completed with result: {result}")
            return result
            
        else:
            log_to_file(f"Module {module_path} has no main function", "WARNING")
            return None
            
    except ImportError as e:
        log_to_file(f"Failed to import module {module_path}: {e}", "ERROR")
        return None
    except Exception as e:
        log_to_file(f"Failed to execute module {module_path}: {e}", "ERROR")
        return None

def run_enabled_modules(modules_path: str, enabled_modules: list) -> dict:
    """Run all enabled modules after schema updates are complete."""
    results = {}
    
    if not enabled_modules:
        log_to_file("No enabled modules to run")
        return results
    
    log_to_file(f"Running {len(enabled_modules)} enabled modules...")
    
    for module_name in enabled_modules:
        try:
            log_to_file(f"Executing module: {module_name}")
            log_to_file("-" * 60)
            log_to_file(f"MODULE: {module_name} - START")
            log_to_file("-" * 60)
            
            # Run the module's main function with output capture
            result = run_update_with_logging(f"modules.{module_name}")
            
            log_to_file("-" * 60)
            log_to_file(f"MODULE: {module_name} - END")
            log_to_file("-" * 60)
            
            # Enhanced result interpretation
            module_result = {
                "executed": result is not None,
                "system_success": False,
                "updated": False,
                "error": None,
                "rollback_success": None,
                "details": result if isinstance(result, dict) else {},
                "self_update_needed": False,
                "restart_attempts": 0
            }
            
            # Check if module needs self-update (returned False)
            if result is False:
                log_message(f"🔄 Module '{module_name}' needs self-update - restarting...")
                module_result["self_update_needed"] = True
                module_result["restart_attempts"] = 1
                
                # Attempt to restart the module once
                try:
                    log_message(f"🔄 Restarting module '{module_name}' after self-update...")
                    restart_result = run_update_with_logging(f"modules.{module_name}")
                    
                    if restart_result is False:
                        log_message(f"⚠️ Module '{module_name}' still needs restart after self-update", "WARNING")
                        module_result["restart_attempts"] = 2
                        module_result["system_success"] = False
                        module_result["error"] = "Module still needs restart after self-update"
                    else:
                        log_message(f"✅ Module '{module_name}' successfully restarted after self-update")
                        module_result["system_success"] = True
                        module_result["updated"] = True
                        
                        # Process the restart result
                        if isinstance(restart_result, dict):
                            module_result["updated"] = restart_result.get("updated", False)
                            module_result["error"] = restart_result.get("error")
                            module_result["rollback_success"] = restart_result.get("rollback_success")
                        
                except Exception as restart_error:
                    log_message(f"✗ Failed to restart module '{module_name}' after self-update: {restart_error}", "ERROR")
                    module_result["system_success"] = False
                    module_result["error"] = f"Restart failed: {restart_error}"
                    
            elif isinstance(result, dict):
                # Module returned detailed status dictionary
                module_result["system_success"] = result.get("success", False)
                module_result["updated"] = result.get("updated", False)
                module_result["error"] = result.get("error")
                module_result["rollback_success"] = result.get("rollback_success")
                
                # Determine overall status message
                if module_result["system_success"]:
                    if module_result["updated"]:
                        log_message(f"✓ Module '{module_name}' executed successfully and updated")
                    else:
                        log_message(f"✓ Module '{module_name}' executed successfully (no update needed)")
                else:
                    if module_result["rollback_success"]:
                        log_message(f"⚠ Module '{module_name}' update failed but system restored successfully", "WARNING")
                    else:
                        log_message(f"✗ Module '{module_name}' execution failed", "ERROR")
            elif result is not None:
                # Module returned something but not a dict - assume success
                module_result["system_success"] = True
                log_message(f"✓ Module '{module_name}' executed successfully")
            else:
                # Module returned None - assume failure
                module_result["system_success"] = False
                log_message(f"✗ Module '{module_name}' execution failed", "ERROR")
            
            results[module_name] = module_result
                
        except Exception as e:
            log_message(f"Failed to execute module '{module_name}': {e}", "ERROR")
            results[module_name] = {
                "executed": False,
                "system_success": False,
                "updated": False,
                "error": str(e),
                "rollback_success": None,
                "details": {},
                "self_update_needed": False,
                "restart_attempts": 0
            }
    
    # Enhanced summary reporting
    total_modules = len(results)
    system_successful = sum(1 for r in results.values() if r["system_success"])
    system_failed = total_modules - system_successful
    modules_updated = sum(1 for r in results.values() if r["updated"])
    modules_restored = sum(1 for r in results.values() if r["rollback_success"])
    modules_self_updated = sum(1 for r in results.values() if r["self_update_needed"])
    
    log_message(f"Module execution completed:")
    log_message(f"  - Total modules: {total_modules}")
    log_message(f"  - System successful: {system_successful}")
    log_message(f"  - System failed: {system_failed}")
    log_message(f"  - Actually updated: {modules_updated}")
    log_message(f"  - Failed but restored: {modules_restored}")
    log_message(f"  - Self-updated and restarted: {modules_self_updated}")
    
    if system_failed > 0:
        failed_modules = [module for module, result in results.items() if not result["system_success"]]
        restored_modules = [module for module, result in results.items() if result["rollback_success"]]
        
        log_message(f"  - Failed modules: {', '.join(failed_modules)}")
        if restored_modules:
            log_message(f"  - Successfully restored: {', '.join(restored_modules)}")
    
    if modules_updated > 0:
        updated_modules = [module for module, result in results.items() if result["updated"]]
        log_message(f"  - Updated modules: {', '.join(updated_modules)}")
    
    if modules_self_updated > 0:
        self_updated_modules = [module for module, result in results.items() if result["self_update_needed"]]
        log_message(f"  - Self-updated modules: {', '.join(self_updated_modules)}")
    
    return results

async def run_schema_based_updates(repo_url: str = None, local_repo_path: str = None, 
                                 modules_path: str = None, branch: str = None) -> dict:
    """
    Main orchestrator for schema-version based updates.
    
    This function implements a bootstrapping-aware update process:
    1. Orchestrator Check: If orchestrator needs updating, update it FIRST and restart
    2. Schema Updates: Compare schema versions and clobber modules that need updating  
    3. Module Execution: Run ALL enabled modules (regardless of whether they were updated)
    
    The orchestrator update phase ensures we're always running the latest orchestrator logic.
    The schema update phase keeps the infrastructure current, while the execution phase
    ensures all enabled services/components are properly configured and running.
    
    Args:
        repo_url: Git repository URL containing updates
        local_repo_path: Local path to clone/sync repository
        modules_path: Path to local modules directory
        branch: Git branch to sync from (if None, reads from index.json)
        
    Returns:
        dict: Results of the update process including both schema updates and executions
    """
    # Use defaults if not provided
    repo_url = repo_url or DEFAULT_REPO_URL
    local_repo_path = local_repo_path or DEFAULT_LOCAL_PATH
    modules_path = modules_path or DEFAULT_MODULES_PATH
    
    # Load branch from global index if not provided
    if branch is None:
        global_index = load_global_index(modules_path)
        branch = global_index.get("metadata", {}).get("branch", "master")
    
    log_to_file("Starting schema-based update orchestration")
    log_to_file(f"Repository: {repo_url}")
    log_to_file(f"Branch: {branch}")
    log_to_file(f"Local modules: {modules_path}")
    log_to_file(f"Sync path: {local_repo_path}")
    # If we are running after an orchestrator self-restart, make that explicit
    if os.environ.get("HS_UPDATER_RESTARTED") == "1":
        log_message("Updater restart complete; proceeding with module updates")
    
    results = {
        "sync_success": False,
        "orchestrator_updated": False,
        "modules_detected": [],
        "modules_updated": {},
        "enabled_modules": [],
        "modules_executed": {},
        "global_index_updated": False,
        "errors": []
    }
    
    try:
        # Step 1: Sync from repository
        log_to_file("Step 1: Syncing from repository...")
        if not sync_from_repo(repo_url, local_repo_path, branch):
            results["errors"].append("Failed to sync from repository")
            return results
        
        results["sync_success"] = True
        
        # Step 1.5: Check if orchestrator itself needs updating
        log_to_file("Step 1.5: Checking orchestrator schema version...")
        orchestrator_needs_update = check_orchestrator_update(modules_path, local_repo_path)
        if orchestrator_needs_update and os.environ.get("HS_UPDATER_RESTARTED") != "1":
            log_to_file("CRITICAL: Orchestrator update detected - updating orchestrator first")
            
            # Update orchestrator IMMEDIATELY and restart once via exec
            log_message("Step 1.6: Updating orchestrator system...")
            orchestrator_success = update_orchestrator(modules_path, local_repo_path)
            if orchestrator_success:
                log_message("Orchestrator updated successfully; restarting updater once before applying module updates…")
                
                # Update global index with new orchestrator version
                update_global_index(modules_path, [], True)
                
                # Update homeserver config timestamp for orchestrator update
                update_homeserver_config_timestamp()
                
                # Prepare exec to replace current process
                shell_script_path = os.path.join(modules_path, "updateManager.sh")
                current_args = sys.argv[1:]  # Skip script name
                shell_args = []
                for arg in current_args:
                    if arg == "--check-only":
                        shell_args.append("--check")
                    elif arg == "--legacy":
                        shell_args.append("--legacy")
                # Set env flag to avoid restart loops
                env = os.environ.copy()
                env["HS_UPDATER_RESTARTED"] = "1"
                
                # Exec the shell script if available; else exec python -m updates.index
                try:
                    if os.path.exists(shell_script_path):
                        log_message("Executing updated updateManager.sh (exec)")
                        os.execve(shell_script_path, [shell_script_path] + shell_args, env)
                    else:
                        log_message("Shell wrapper not found; exec Python module directly (exec)")
                        exec_argv = [sys.executable, "-m", "updates.index"] + current_args
                        os.execve(sys.executable, exec_argv, env)
                except Exception as e:
                    # If exec fails, treat as critical error
                    log_message(f"Failed to exec updated orchestrator: {e}", "ERROR")
                    results["errors"].append("Failed to exec updated orchestrator")
                    return results
            else:
                results["errors"].append("Failed to update orchestrator")
                return results
        
        # Step 2: Detect modules that need updates (only reached if orchestrator didn't need updating)
        log_message("Step 2: Detecting module updates...")
        repo_modules_path = os.path.join(local_repo_path, "modules")  # Look for modules subdirectory
        if not os.path.exists(repo_modules_path):
            repo_modules_path = local_repo_path  # Fallback to root if no modules subdirectory
        
        # Ensure local modules path has modules subdirectory
        local_modules_search_path = os.path.join(modules_path, "modules")
        if not os.path.exists(local_modules_search_path):
            local_modules_search_path = modules_path  # Fallback to root
        
        if DEBUG:
            log_message(f"🔍 Calling detect_module_updates with:")
            log_message(f"  Local modules path: {modules_path}")
            log_message(f"  Repository modules path: {repo_modules_path}")
        
        modules_to_update = detect_module_updates(modules_path, repo_modules_path)
        results["modules_detected"] = modules_to_update
        
        if DEBUG:
            log_message(f"🎯 detect_module_updates returned: {modules_to_update}")
        
        if modules_to_update:
            log_message(f"Found {len(modules_to_update)} modules to update: {', '.join(modules_to_update)}")
        else:
            log_message("No modules need updating")
        
        # Step 3: Update modules
        if modules_to_update:
            log_message("Step 3: Updating modules...")
            update_results = update_modules(modules_to_update, modules_path, repo_modules_path)
            results["modules_updated"] = update_results
        
        # Step 4: Get all enabled modules and run them
        log_message("Step 4: Getting enabled modules...")
        enabled_modules = get_enabled_modules(modules_path)
        results["enabled_modules"] = enabled_modules
        
        if enabled_modules:
            log_message("Step 5: Running all enabled modules...")
            log_message("Note: Modules are executed regardless of whether they were schema-updated")
            log_message("This ensures content and tab updates are handled after schema updates")
            module_execution_results = run_enabled_modules(modules_path, enabled_modules)
            results["modules_executed"] = module_execution_results
        else:
            log_message("No enabled modules found to execute")
            results["modules_executed"] = {}
        
        # Step 6: Update global index
        log_message("Step 6: Updating global index...")
        successful_updates = [module for module, success in results["modules_updated"].items() if success] if results["modules_updated"] else []
        if successful_updates:
            results["global_index_updated"] = update_global_index(modules_path, successful_updates, False, repo_modules_path)
        
        # Step 7: Update homeserver config timestamp
        log_message("Step 7: Updating homeserver config timestamp...")
        homeserver_timestamp_updated = update_homeserver_config_timestamp()
        results["homeserver_timestamp_updated"] = homeserver_timestamp_updated
        
        # Enhanced Summary with detailed module status reporting
        schema_updated_count = sum(1 for success in results["modules_updated"].values() if success) if results["modules_updated"] else 0
        schema_failed_count = len(results["modules_updated"]) - schema_updated_count if results["modules_updated"] else 0
        
        # Enhanced execution result analysis
        execution_results = results["modules_executed"]
        total_executed = len(execution_results)
        system_successful = sum(1 for r in execution_results.values() if r["system_success"]) if execution_results else 0
        system_failed = total_executed - system_successful
        modules_actually_updated = sum(1 for r in execution_results.values() if r["updated"]) if execution_results else 0
        modules_restored = sum(1 for r in execution_results.values() if r["rollback_success"]) if execution_results else 0
        
        log_message(f"Update orchestration completed:")
        log_message(f"  - Schema updates detected: {len(modules_to_update)}")
        log_message(f"  - Successfully schema updated: {schema_updated_count}")
        log_message(f"  - Failed schema updates: {schema_failed_count}")
        log_message(f"  - Enabled modules found: {len(enabled_modules)}")
        log_message(f"  - System successful: {system_successful}")
        log_message(f"  - System failed: {system_failed}")
        log_message(f"  - Actually updated: {modules_actually_updated}")
        log_message(f"  - Failed but restored: {modules_restored}")
        
        if schema_failed_count > 0:
            failed_modules = [module for module, success in results["modules_updated"].items() if not success]
            log_message(f"  - Failed schema updates: {', '.join(failed_modules)}")
        
        if system_failed > 0:
            failed_executions = [module for module, result in execution_results.items() if not result["system_success"]]
            restored_executions = [module for module, result in execution_results.items() if result["rollback_success"]]
            log_message(f"  - Failed executions: {', '.join(failed_executions)}")
            if restored_executions:
                log_message(f"  - Successfully restored: {', '.join(restored_executions)}")
        
        if modules_actually_updated > 0:
            updated_executions = [module for module, result in execution_results.items() if result["updated"]]
            log_message(f"  - Successfully updated: {', '.join(updated_executions)}")
        
    except Exception as e:
        error_msg = f"Unhandled error in update orchestration: {e}"
        log_message(error_msg, "ERROR")
        results["errors"].append(error_msg)
        import traceback
        traceback.print_exc()
    
    return results

def run_legacy_updates():
    """
    Fallback to run legacy manifest-based updates if needed.
    This maintains backward compatibility with the old system.
    """
    log_message("Running legacy update system...")
    
    try:
        # Try to load and run the old manifest system
        base_dir = os.path.dirname(os.path.abspath(__file__))
        manifest_path = os.path.join(base_dir, 'manifest.json')
        
        if os.path.exists(manifest_path):
            import json
            with open(manifest_path, 'r') as f:
                manifest = json.load(f)
            
            # Run updates based on old manifest structure
            updates = {u['name']: u for u in manifest.get('updates', [])}
            entrypoint = manifest.get('entrypoint', 'all_services')
            
            if entrypoint in updates:
                entry = updates[entrypoint]
                children = entry.get('children', [])
                
                log_message(f"Running legacy updates for: {', '.join(children)}")
                
                for child_name in children:
                    try:
                        from . import run_update
                        run_update(child_name)
                    except Exception as e:
                        log_message(f"Legacy update failed for {child_name}: {e}", "ERROR")
            
        else:
            log_message("No legacy manifest found", "WARNING")
            
    except Exception as e:
        log_message(f"Legacy update system failed: {e}", "ERROR")

def enable_module(modules_path: str, module_name: str) -> bool:
    """Enable a module by setting enabled=true in its index.json"""
    try:
        module_path = os.path.join(modules_path, "modules", module_name)
        if not os.path.exists(module_path):
            module_path = os.path.join(modules_path, module_name)
        
        if not os.path.exists(module_path):
            log_message(f"Module '{module_name}' not found", "ERROR")
            return False
        
        index_file = os.path.join(module_path, "index.json")
        if not os.path.exists(index_file):
            log_message(f"Module '{module_name}' has no index.json", "ERROR")
            return False
        
        with open(index_file, 'r') as f:
            config = json.load(f)
        
        config["metadata"]["enabled"] = True
        
        with open(index_file, 'w') as f:
            json.dump(config, f, indent=4)
        
        log_message(f"✓ Module '{module_name}' enabled")
        return True
        
    except Exception as e:
        log_message(f"Failed to enable module '{module_name}': {e}", "ERROR")
        return False

def disable_module(modules_path: str, module_name: str) -> bool:
    """Disable a module by setting enabled=false in its index.json"""
    try:
        module_path = os.path.join(modules_path, "modules", module_name)
        if not os.path.exists(module_path):
            module_path = os.path.join(modules_path, module_name)
        
        if not os.path.exists(module_path):
            log_message(f"Module '{module_name}' not found", "ERROR")
            return False
        
        index_file = os.path.join(module_path, "index.json")
        if not os.path.exists(index_file):
            log_message(f"Module '{module_name}' has no index.json", "ERROR")
            return False
        
        with open(index_file, 'r') as f:
            config = json.load(f)
        
        config["metadata"]["enabled"] = False
        
        with open(index_file, 'w') as f:
            json.dump(config, f, indent=4)
        
        log_message(f"✓ Module '{module_name}' disabled")
        return True
        
    except Exception as e:
        log_message(f"Failed to disable module '{module_name}': {e}", "ERROR")
        return False

def enable_component(modules_path: str, module_name: str, component_name: str) -> bool:
    """Enable a component within a module"""
    try:
        module_path = os.path.join(modules_path, "modules", module_name)
        if not os.path.exists(module_path):
            module_path = os.path.join(modules_path, module_name)
        
        if not os.path.exists(module_path):
            log_message(f"Module '{module_name}' not found", "ERROR")
            return False
        
        index_file = os.path.join(module_path, "index.json")
        if not os.path.exists(index_file):
            log_message(f"Module '{module_name}' has no index.json", "ERROR")
            return False
        
        with open(index_file, 'r') as f:
            config = json.load(f)
        
        # Look for component in various possible locations
        components = None
        if "config" in config and "target_paths" in config["config"] and "components" in config["config"]["target_paths"]:
            components = config["config"]["target_paths"]["components"]
        elif "config" in config and "components" in config["config"]:
            components = config["config"]["components"]
        
        if not components or component_name not in components:
            log_message(f"Component '{component_name}' not found in module '{module_name}'", "ERROR")
            return False
        
        components[component_name]["enabled"] = True
        
        with open(index_file, 'w') as f:
            json.dump(config, f, indent=4)
        
        log_message(f"✓ Component '{component_name}' enabled in module '{module_name}'")
        return True
        
    except Exception as e:
        log_message(f"Failed to enable component '{component_name}' in module '{module_name}': {e}", "ERROR")
        return False

def disable_component(modules_path: str, module_name: str, component_name: str) -> bool:
    """Disable a component within a module"""
    try:
        module_path = os.path.join(modules_path, "modules", module_name)
        if not os.path.exists(module_path):
            module_path = os.path.join(modules_path, module_name)
        
        if not os.path.exists(module_path):
            log_message(f"Module '{module_name}' not found", "ERROR")
            return False
        
        index_file = os.path.join(module_path, "index.json")
        if not os.path.exists(index_file):
            log_message(f"Module '{module_name}' has no index.json", "ERROR")
            return False
        
        with open(index_file, 'r') as f:
            config = json.load(f)
        
        # Look for component in various possible locations
        components = None
        if "config" in config and "target_paths" in config["config"] and "components" in config["config"]["target_paths"]:
            components = config["config"]["target_paths"]["components"]
        elif "config" in config and "components" in config["config"]:
            components = config["config"]["components"]
        
        if not components or component_name not in components:
            log_message(f"Component '{component_name}' not found in module '{module_name}'", "ERROR")
            return False
        
        components[component_name]["enabled"] = False
        
        with open(index_file, 'w') as f:
            json.dump(config, f, indent=4)
        
        log_message(f"✓ Component '{component_name}' disabled in module '{module_name}'")
        return True
        
    except Exception as e:
        log_message(f"Failed to disable component '{component_name}' in module '{module_name}': {e}", "ERROR")
        return False

def list_modules(modules_path: str) -> bool:
    """List all modules with their status"""
    try:
        modules_search_path = os.path.join(modules_path, "modules")
        if not os.path.exists(modules_search_path):
            modules_search_path = modules_path
        
        if not os.path.exists(modules_search_path):
            log_message("No modules directory found", "ERROR")
            return False
        
        modules = []
        for item in os.listdir(modules_search_path):
            item_path = os.path.join(modules_search_path, item)
            if os.path.isdir(item_path):
                # Exclude backup directories from listing
                if item.endswith('.backup'):
                    continue
                index_file = os.path.join(item_path, "index.json")
                if os.path.exists(index_file):
                    try:
                        with open(index_file, 'r') as f:
                            config = json.load(f)
                        
                        enabled = config.get("metadata", {}).get("enabled", True)
                        schema_version = config.get("metadata", {}).get("schema_version", "unknown")
                        description = config.get("metadata", {}).get("description", "No description")
                        
                        modules.append({
                            "name": item,
                            "enabled": enabled,
                            "version": schema_version,
                            "description": description
                        })
                    except Exception as e:
                        log_message(f"Error reading module '{item}': {e}", "WARNING")
        
        if not modules:
            log_message("No modules found")
            return True
        
        # Sort by name
        modules.sort(key=lambda x: x["name"])
        
        log_message("Available modules:")
        log_message("-" * 80)
        for module in modules:
            status = "ENABLED" if module["enabled"] else "DISABLED"
            log_message(f"{module['name']:<15} {status:<10} v{module['version']:<10} {module['description']}")
        
        enabled_count = sum(1 for m in modules if m["enabled"])
        log_message("-" * 80)
        log_message(f"Total: {len(modules)} modules ({enabled_count} enabled, {len(modules) - enabled_count} disabled)")
        
        return True
        
    except Exception as e:
        log_message(f"Failed to list modules: {e}", "ERROR")
        return False

def get_module_status(modules_path: str, module_name: str = None) -> bool:
    """Get status for a specific module or all modules"""
    try:
        if module_name:
            # Get status for specific module
            module_path = os.path.join(modules_path, "modules", module_name)
            if not os.path.exists(module_path):
                module_path = os.path.join(modules_path, module_name)
            
            if not os.path.exists(module_path):
                log_message(f"Module '{module_name}' not found", "ERROR")
                return False
            
            index_file = os.path.join(module_path, "index.json")
            if not os.path.exists(index_file):
                log_message(f"Module '{module_name}' has no index.json", "ERROR")
                return False
            
            with open(index_file, 'r') as f:
                config = json.load(f)
            
            enabled = config.get("metadata", {}).get("enabled", True)
            schema_version = config.get("metadata", {}).get("schema_version", "unknown")
            description = config.get("metadata", {}).get("description", "No description")
            
            log_message(f"Module: {module_name}")
            log_message(f"Status: {'ENABLED' if enabled else 'DISABLED'}")
            log_message(f"Version: {schema_version}")
            log_message(f"Description: {description}")
            
            # Show components if they exist
            components = None
            if "config" in config and "target_paths" in config["config"] and "components" in config["config"]["target_paths"]:
                components = config["config"]["target_paths"]["components"]
            elif "config" in config and "components" in config["config"]:
                components = config["config"]["components"]
            
            if components:
                log_message("Components:")
                for comp_name, comp_config in components.items():
                    comp_enabled = comp_config.get("enabled", True)
                    comp_desc = comp_config.get("description", "No description")
                    status = "ENABLED" if comp_enabled else "DISABLED"
                    log_message(f"  {comp_name:<15} {status:<10} {comp_desc}")
            
            return True
        else:
            # Get status for all modules (same as list_modules)
            return list_modules(modules_path)
        
    except Exception as e:
        log_message(f"Failed to get module status: {e}", "ERROR")
        return False

def main():
    """
    Main entry point for the update orchestrator.
    Supports both new schema-based and legacy manifest-based updates.
    """
    parser = argparse.ArgumentParser(description="Homeserver Update Orchestrator")
    parser.add_argument("--repo-url", default=DEFAULT_REPO_URL, 
                       help="Git repository URL for updates")
    parser.add_argument("--local-repo", default=DEFAULT_LOCAL_PATH,
                       help="Local path to sync repository")
    parser.add_argument("--modules-path", default=DEFAULT_MODULES_PATH,
                       help="Path to local modules directory")
    parser.add_argument("--branch", default=None,
                       help="Git branch to sync from (default: read from index.json)")
    parser.add_argument("--legacy", action="store_true",
                       help="Use legacy manifest-based updates")
    parser.add_argument("--check-only", action="store_true",
                       help="Only check for updates, don't apply them")
    
    # Module management arguments
    parser.add_argument("--enable-module", metavar="MODULE",
                       help="Enable a module")
    parser.add_argument("--disable-module", metavar="MODULE",
                       help="Disable a module")
    parser.add_argument("--enable-component", nargs=2, metavar=("MODULE", "COMPONENT"),
                       help="Enable a component in a module")
    parser.add_argument("--disable-component", nargs=2, metavar=("MODULE", "COMPONENT"),
                       help="Disable a component in a module")
    parser.add_argument("--list-modules", action="store_true",
                       help="List all modules with status")
    parser.add_argument("--module-status", metavar="MODULE",
                       help="Get status for a specific module")
    parser.add_argument("--all-status", action="store_true",
                       help="Get status for all modules")
    
    args = parser.parse_args()
    
    try:
        # Initialize global logging system FIRST
        setup_global_update_logging()
        
        # Handle module management operations first
        if args.enable_module:
            success = enable_module(args.modules_path, args.enable_module)
            sys.exit(0 if success else 1)
        
        elif args.disable_module:
            success = disable_module(args.modules_path, args.disable_module)
            sys.exit(0 if success else 1)
        
        elif args.enable_component:
            module_name, component_name = args.enable_component
            success = enable_component(args.modules_path, module_name, component_name)
            sys.exit(0 if success else 1)
        
        elif args.disable_component:
            module_name, component_name = args.disable_component
            success = disable_component(args.modules_path, module_name, component_name)
            sys.exit(0 if success else 1)
        
        elif args.list_modules:
            success = list_modules(args.modules_path)
            sys.exit(0 if success else 1)
        
        elif args.module_status:
            success = get_module_status(args.modules_path, args.module_status)
            sys.exit(0 if success else 1)
        
        elif args.all_status:
            success = get_module_status(args.modules_path)
            sys.exit(0 if success else 1)
        
        # Handle update operations
        elif args.legacy:
            # Run legacy system
            run_legacy_updates()
        else:
            # Load branch from global index if not provided
            if args.branch is None:
                global_index = load_global_index(args.modules_path)
                args.branch = global_index.get("metadata", {}).get("branch", "master")
                log_message(f"Using branch from index.json: {args.branch}")
            
            # Run new schema-based system
            if args.check_only:
                log_message("Check-only mode: detecting updates without applying...")
                
                # Step 0: Check orchestrator update first
                orchestrator_update_available = False
                if sync_from_repo(args.repo_url, args.local_repo, args.branch):
                    orchestrator_needs_update = check_orchestrator_update(args.modules_path, args.local_repo)
                    if orchestrator_needs_update:
                        orchestrator_update_available = True
                        log_message("Orchestrator update available")
                    else:
                        log_message("Orchestrator is up to date")
                else:
                    log_message("Failed to sync repository for orchestrator check", "ERROR")
                    return
                
                # Step 1: Schema-level check (existing functionality)
                schema_updates_available = []
                repo_modules_path = os.path.join(args.local_repo, "modules")
                if not os.path.exists(repo_modules_path):
                    repo_modules_path = args.local_repo
                
                modules_to_update = detect_module_updates(args.modules_path, repo_modules_path)
                schema_updates_available = modules_to_update
                
                if modules_to_update:
                    log_message("Schema updates available:")
                    for module in modules_to_update:
                        log_message(f"  - {module} (schema update needed)")
                else:
                    log_message("All module schemas are up to date")
                
                # Step 2: OS module content check (focused approach)
                log_message("Checking OS module for available package updates...")
                enabled_modules = get_enabled_modules(args.modules_path)
                content_updates_available = []
                
                # Only check OS module for deeper content updates
                if "os" in enabled_modules:
                    try:
                        # Import and run the OS module's check functionality
                        from . import run_update
                        check_result = run_update("modules.os", ["--check"])
                        
                        if isinstance(check_result, dict) and check_result.get("upgradable", 0) > 0:
                            count = check_result.get("upgradable", 0)
                            log_message(f"  - OS module: {count} packages available for upgrade")
                            content_updates_available.append({
                                "module": "os",
                                "count": count,
                                "details": check_result
                            })
                        else:
                            log_message("  - OS module: No package updates available")
                            
                    except Exception as e:
                        log_message(f"  - OS module check failed: {e}", "WARNING")
                else:
                    log_message("  - OS module not enabled, skipping package check")
                
                # Summary
                log_message("Check summary:")
                if orchestrator_update_available:
                    log_message("  - Orchestrator update available")
                if schema_updates_available:
                    log_message(f"  - Schema updates: {len(schema_updates_available)} modules")
                if content_updates_available:
                    total_content_items = sum(item["count"] for item in content_updates_available)
                    log_message(f"  - Content updates: {total_content_items} items across {len(content_updates_available)} modules")
                
                if not orchestrator_update_available and not schema_updates_available and not content_updates_available:
                    log_message("  - No updates available")
                else:
                    log_message("  - Updates are available - run without --check to apply them")
            else:
                # Full update process
                if sys.version_info >= (3, 7):
                    results = asyncio.run(run_schema_based_updates(
                        args.repo_url, args.local_repo, args.modules_path, args.branch
                    ))
                else:
                    loop = asyncio.get_event_loop()
                    results = loop.run_until_complete(run_schema_based_updates(
                        args.repo_url, args.local_repo, args.modules_path, args.branch
                    ))
                
                # Check if orchestrator was restarted (successful completion)
                if results.get("orchestrator_restarted"):
                    log_message("Orchestrator was updated and restarted successfully")
                    sys.exit(0)
                
                # Enhanced exit logic with better failure classification
                has_errors = bool(results.get("errors"))
                sync_failed = not results.get("sync_success")
                execution_results = results.get("modules_executed", {})
                
                # Count different types of failures
                system_failures = sum(1 for r in execution_results.values() if not r["system_success"]) if execution_results else 0
                unrestored_failures = sum(1 for r in execution_results.values() if not r["system_success"] and not r["rollback_success"]) if execution_results else 0
                
                # Only exit with error if there are critical system failures
                critical_failures = has_errors or sync_failed or unrestored_failures > 0
                
                if critical_failures:
                    if has_errors:
                        log_message("Exiting due to system errors", "ERROR")
                    if sync_failed:
                        log_message("Exiting due to sync failure", "ERROR") 
                    if unrestored_failures > 0:
                        log_message("Exiting due to unrecoverable module failures", "ERROR")
                    sys.exit(1)
                else:
                    # System is stable - modules that failed were restored successfully
                    if system_failures > 0:
                        log_message("Some modules failed to update but system is stable (all failures restored)", "WARNING")
                    log_message("Update orchestration completed successfully")
                    sys.exit(0)
                    
    except KeyboardInterrupt:
        log_message("Update process interrupted by user", "WARNING")
        sys.exit(130)
    except Exception as e:
        log_message(f"Unhandled error in update process: {e}", "ERROR")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
