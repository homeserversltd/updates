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
            import json
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

def update_global_index(modules_path: str, updated_modules: list) -> bool:
    """Update the global index.json with new module versions."""
    try:
        import json
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
        
        # Write updated index
        with open(index_file, 'w') as f:
            json.dump(global_index, f, indent=4)
        
        log_message(f"Global index updated with {len(updated_modules)} modules")
        return True
        
    except Exception as e:
        log_message(f"Failed to update global index: {e}", "ERROR")
        return False

async def run_schema_based_updates(repo_url: str = None, local_repo_path: str = None, 
                                 modules_path: str = None, branch: str = "main") -> dict:
    """
    Main orchestrator for schema-version based updates.
    
    Args:
        repo_url: Git repository URL containing updates
        local_repo_path: Local path to clone/sync repository
        modules_path: Path to local modules directory
        branch: Git branch to sync from
        
    Returns:
        dict: Results of the update process
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
        "modules_detected": [],
        "modules_updated": {},
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
        
        if not modules_to_update:
            log_message("No modules need updates")
            return results
        
        log_message(f"Found {len(modules_to_update)} modules to update: {', '.join(modules_to_update)}")
        
        # Step 3: Update modules
        log_message("Step 3: Updating modules...")
        update_results = update_modules(modules_to_update, modules_path, repo_modules_path)
        results["modules_updated"] = update_results
        
        # Step 4: Update global index
        log_message("Step 4: Updating global index...")
        successful_updates = [module for module, success in update_results.items() if success]
        if successful_updates:
            results["global_index_updated"] = update_global_index(modules_path, successful_updates)
        
        # Summary
        successful_count = sum(1 for success in update_results.values() if success)
        failed_count = len(update_results) - successful_count
        
        log_message(f"Update orchestration completed:")
        log_message(f"  - Modules detected: {len(modules_to_update)}")
        log_message(f"  - Successfully updated: {successful_count}")
        log_message(f"  - Failed updates: {failed_count}")
        
        if failed_count > 0:
            failed_modules = [module for module, success in update_results.items() if not success]
            log_message(f"  - Failed modules: {', '.join(failed_modules)}")
        
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
    
    args = parser.parse_args()
    
    try:
        if args.legacy:
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
                
                # Exit with error code if updates failed
                if results.get("errors") or not results.get("sync_success"):
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
