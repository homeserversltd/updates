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
from pathlib import Path

# Add current directory to path for relative imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import from the current package using relative imports
from . import (
    log_message,
    sync_from_repo,
    detect_module_updates,
    update_modules,
    load_module_index
)

# Configuration
DEFAULT_REPO_URL = "https://github.com/homeserverltd/updates.git"
DEFAULT_LOCAL_PATH = "/tmp/homeserver-updates-repo"
DEFAULT_MODULES_PATH = "/var/local/lib/updates"

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
            "channel": "stable"
        },
        "packages": {}
    }

def update_global_index(modules_path: str, updated_modules: list, orchestrator_updated: bool = False) -> bool:
    """Update the global index.json with new module versions and orchestrator schema version."""
    try:
        index_file = os.path.join(modules_path, "index.json")
        global_index = load_global_index(modules_path)
        
        # Update package versions based on updated modules
        for module_name in updated_modules:
            module_path = os.path.join(modules_path, module_name)
            module_index = load_module_index(module_path)
            if module_index:
                schema_version = module_index.get("metadata", {}).get("schema_version", "1.0.0")
                global_index["packages"][module_name] = schema_version
                log_message(f"Updated global index: {module_name} → {schema_version}")
        
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
        from . import compare_schema_versions
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
    """Update the orchestrator system files from repository."""
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
                
                log_message(f"Updated: {file_name}")
            else:
                log_message(f"File not found in repository: {file_name}", "WARNING")
        
        # Update the index.json with new orchestrator version
        repo_index_path = os.path.join(repo_path, "index.json")
        local_index_path = os.path.join(modules_path, "index.json")
        
        if os.path.exists(repo_index_path):
            shutil.copy2(repo_index_path, local_index_path)
            log_message("Updated: index.json")
        
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

def run_enabled_modules(modules_path: str, enabled_modules: list) -> dict:
    """Run all enabled modules after schema updates are complete."""
    results = {}
    
    if not enabled_modules:
        log_message("No enabled modules to run")
        return results
    
    log_message(f"Running {len(enabled_modules)} enabled modules...")
    
    for module_name in enabled_modules:
        try:
            log_message(f"Executing module: {module_name}")
            
            # Import the run_update function from __init__.py
            from . import run_update
            
            # Run the module's main function
            result = run_update(f"modules.{module_name}")
            results[module_name] = result is not None
            
            if results[module_name]:
                log_message(f"✓ Module '{module_name}' executed successfully")
            else:
                log_message(f"✗ Module '{module_name}' execution failed", "ERROR")
                
        except Exception as e:
            log_message(f"Failed to execute module '{module_name}': {e}", "ERROR")
            results[module_name] = False
    
    successful_count = sum(1 for success in results.values() if success)
    failed_count = len(results) - successful_count
    
    log_message(f"Module execution completed: {successful_count} successful, {failed_count} failed")
    
    if failed_count > 0:
        failed_modules = [module for module, success in results.items() if not success]
        log_message(f"Failed modules: {', '.join(failed_modules)}")
    
    return results

async def run_schema_based_updates(repo_url: str = None, local_repo_path: str = None, 
                                 modules_path: str = None, branch: str = "main") -> dict:
    """
    Main orchestrator for schema-version based updates.
    
    This function implements the two-phase update process:
    1. Schema Updates: Compare schema versions and clobber modules that need updating
    2. Module Execution: Run ALL enabled modules (regardless of whether they were updated)
    
    The schema update phase keeps the infrastructure current, while the execution phase
    ensures all enabled services/components are properly configured and running.
    
    Args:
        repo_url: Git repository URL containing updates
        local_repo_path: Local path to clone/sync repository
        modules_path: Path to local modules directory
        branch: Git branch to sync from
        
    Returns:
        dict: Results of the update process including both schema updates and executions
    """
    # Use defaults if not provided
    repo_url = repo_url or DEFAULT_REPO_URL
    local_repo_path = local_repo_path or DEFAULT_LOCAL_PATH
    modules_path = modules_path or DEFAULT_MODULES_PATH
    
    log_message("Starting schema-based update orchestration")
    log_message(f"Repository: {repo_url}")
    log_message(f"Local modules: {modules_path}")
    log_message(f"Sync path: {local_repo_path}")
    
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
        log_message("Step 1: Syncing from repository...")
        if not sync_from_repo(repo_url, local_repo_path, branch):
            results["errors"].append("Failed to sync from repository")
            return results
        
        results["sync_success"] = True
        
        # Step 1.5: Check if orchestrator itself needs updating
        log_message("Step 1.5: Checking orchestrator schema version...")
        orchestrator_needs_update = check_orchestrator_update(modules_path, local_repo_path)
        if orchestrator_needs_update:
            log_message("CRITICAL: Orchestrator update detected - system will restart after module updates")
            results["orchestrator_updated"] = True
        
        # Step 2: Detect modules that need updates
        log_message("Step 2: Detecting module updates...")
        repo_modules_path = os.path.join(local_repo_path, "modules")  # Look for modules subdirectory
        if not os.path.exists(repo_modules_path):
            repo_modules_path = local_repo_path  # Fallback to root if no modules subdirectory
        
        # Ensure local modules path has modules subdirectory
        local_modules_search_path = os.path.join(modules_path, "modules")
        if not os.path.exists(local_modules_search_path):
            local_modules_search_path = modules_path  # Fallback to root
        
        modules_to_update = detect_module_updates(modules_path, repo_modules_path)
        results["modules_detected"] = modules_to_update
        
        # Always continue to run enabled modules, even if no schema updates needed
        log_message(f"Schema updates needed: {len(modules_to_update)} modules, orchestrator: {orchestrator_needs_update}")
        
        if modules_to_update:
            log_message(f"Found {len(modules_to_update)} modules to update: {', '.join(modules_to_update)}")
        
        # Step 3: Update modules
        if modules_to_update:
            log_message("Step 3: Updating modules...")
            update_results = update_modules(modules_to_update, modules_path, repo_modules_path)
            results["modules_updated"] = update_results
        
        # Step 4: Update orchestrator if needed (AFTER modules)
        if orchestrator_needs_update:
            log_message("Step 4: Updating orchestrator system...")
            orchestrator_success = update_orchestrator(modules_path, local_repo_path)
            if orchestrator_success:
                log_message("Orchestrator updated successfully - restart required")
                results["orchestrator_restart_required"] = True
            else:
                results["errors"].append("Failed to update orchestrator")
        
        # Step 5: Get all enabled modules and run them
        log_message("Step 5: Getting enabled modules...")
        enabled_modules = get_enabled_modules(modules_path)
        results["enabled_modules"] = enabled_modules
        
        if enabled_modules:
            log_message("Step 6: Running all enabled modules...")
            module_execution_results = run_enabled_modules(modules_path, enabled_modules)
            results["modules_executed"] = module_execution_results
        else:
            log_message("No enabled modules found to execute")
            results["modules_executed"] = {}
        
        # Step 7: Update global index
        log_message("Step 7: Updating global index...")
        successful_updates = [module for module, success in results["modules_updated"].items() if success] if results["modules_updated"] else []
        if successful_updates or orchestrator_needs_update:
            results["global_index_updated"] = update_global_index(modules_path, successful_updates, orchestrator_needs_update)
        
        # Summary
        schema_updated_count = sum(1 for success in results["modules_updated"].values() if success) if results["modules_updated"] else 0
        schema_failed_count = len(results["modules_updated"]) - schema_updated_count if results["modules_updated"] else 0
        
        executed_count = sum(1 for success in results["modules_executed"].values() if success) if results["modules_executed"] else 0
        execution_failed_count = len(results["modules_executed"]) - executed_count if results["modules_executed"] else 0
        
        log_message(f"Update orchestration completed:")
        log_message(f"  - Schema updates detected: {len(modules_to_update)}")
        log_message(f"  - Successfully schema updated: {schema_updated_count}")
        log_message(f"  - Failed schema updates: {schema_failed_count}")
        log_message(f"  - Enabled modules found: {len(enabled_modules)}")
        log_message(f"  - Successfully executed: {executed_count}")
        log_message(f"  - Failed executions: {execution_failed_count}")
        log_message(f"  - Orchestrator updated: {orchestrator_needs_update}")
        
        if schema_failed_count > 0:
            failed_modules = [module for module, success in results["modules_updated"].items() if not success]
            log_message(f"  - Failed schema updates: {', '.join(failed_modules)}")
        
        if execution_failed_count > 0:
            failed_executions = [module for module, success in results["modules_executed"].items() if not success]
            log_message(f"  - Failed executions: {', '.join(failed_executions)}")
        
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
    parser.add_argument("--branch", default="main",
                       help="Git branch to sync from")
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
            # Run new schema-based system
            if args.check_only:
                log_message("Check-only mode: detecting updates without applying...")
                # Just sync and detect, don't update
                if sync_from_repo(args.repo_url, args.local_repo, args.branch):
                    repo_modules_path = os.path.join(args.local_repo, "updates")
                    if not os.path.exists(repo_modules_path):
                        repo_modules_path = args.local_repo
                    
                    modules_to_update = detect_module_updates(args.modules_path, repo_modules_path)
                    if modules_to_update:
                        log_message(f"Updates available for: {', '.join(modules_to_update)}")
                    else:
                        log_message("All modules are up to date")
                else:
                    log_message("Failed to sync repository for check", "ERROR")
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
                
                # Exit with error code if critical failures occurred
                has_errors = bool(results.get("errors"))
                sync_failed = not results.get("sync_success")
                execution_failures = results.get("modules_executed", {})
                critical_execution_failures = sum(1 for success in execution_failures.values() if not success) > 0
                
                if has_errors or sync_failed or critical_execution_failures:
                    if has_errors:
                        log_message("Exiting due to system errors", "ERROR")
                    if sync_failed:
                        log_message("Exiting due to sync failure", "ERROR") 
                    if critical_execution_failures:
                        log_message("Exiting due to module execution failures", "ERROR")
                    sys.exit(1)
                    
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
