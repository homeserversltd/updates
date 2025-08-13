#!/usr/bin/env python3
"""
HOMESERVER Update Management System
Copyright (C) 2024 HOMESERVER LLC

HOMESERVER Website Update Module

Modular website update system that handles updating the HOMESERVER web interface 
from the GitHub repository with component-based architecture and existing utilities.

Key Features:
- Component-based architecture for better maintainability
- Uses existing utils (StateManager, PermissionManager, version control)
- Non-destructive file operations with detailed logging
- Graceful failure handling with automatic rollback
- npm build process management with service restart validation
"""

import json
import os
import time
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from datetime import datetime

# Import existing utilities
from updates.index import log_message, compare_schema_versions
from updates.utils.state_manager import StateManager
from updates.utils.permissions import PermissionManager, PermissionTarget

# Import our new components
from .components import GitOperations, FileOperations, BuildManager, MaintenanceManager


class WebsiteUpdateError(Exception):
    """Custom exception for website update failures."""
    pass


class WebsiteUpdater:
    """
    Main website updater class that orchestrates the update process.
    
    Uses component-based architecture and existing utilities for:
    - Git operations (cloning, version checking)
    - File operations (safe copying, config preservation)  
    - Build management (npm install/build, service restart)
    - State management (backup/restore via StateManager)
    - Permission management (via PermissionManager)
    """
    
    def __init__(self, module_path: str = None):
        if module_path is None:
            module_path = os.path.dirname(os.path.abspath(__file__))
        
        self.module_path = Path(module_path)
        self.index_file = self.module_path / "index.json"
        self.config = self._load_config()
        
        # Initialize components
        self.git = GitOperations(self.config)
        self.files = FileOperations(self.config)
        self.build = BuildManager(self.config)
        self.maintenance = MaintenanceManager(self.config)
        
        # Initialize existing utilities
        self.state_manager = StateManager("/var/backups/website")
        self.permission_manager = PermissionManager("website")
        
    def _load_config(self) -> Dict[str, Any]:
        """Load the website configuration from index.json."""
        try:
            with open(self.index_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            log_message(f"Failed to load website config: {e}", "ERROR")
            return {}
    
    def _get_local_version(self) -> Optional[str]:
        """Get the local version from homeserver.json."""
        try:
            version_config = self.config.get('config', {}).get('version_checking', {})
            version_file = version_config.get('content_version_file', 'src/config/homeserver.json')
            version_path_components = version_config.get('content_version_path', 'global.version.version').split('.')
            
            base_dir = self.config.get('config', {}).get('target_paths', {}).get('base_directory', '/var/www/homeserver')
            local_config_path = os.path.join(base_dir, version_file)
            
            if not os.path.exists(local_config_path):
                log_message(f"Local homeserver.json not found at {local_config_path}", "WARNING")
                return None
            
            with open(local_config_path, 'r') as f:
                config_data = json.load(f)
            
            # Navigate through the nested path
            version = config_data
            for component in version_path_components:
                if isinstance(version, dict) and component in version:
                    version = version[component]
                else:
                    log_message(f"Version path {'.'.join(version_path_components)} not found", "WARNING")
                    return None
            
            if isinstance(version, str):
                log_message(f"Local version: {version}")
                return version
            else:
                log_message(f"Version is not a string: {version}", "WARNING")
                return None
                
        except Exception as e:
            log_message(f"Failed to read local version: {e}", "ERROR")
            return None
    
    def _check_version_update_needed(self, temp_dir: str) -> Tuple[bool, bool, Dict[str, Any]]:
        """
        Check if an update is needed by comparing both schema and content versions.
        
        Returns:
            Tuple[bool, bool, Dict]: (update_needed, nuclear_restore_needed, update_details)
        """
        update_details = {
            "schema_update_needed": False,
            "content_update_needed": False,
            "local_schema_version": None,
            "repo_schema_version": None,
            "local_content_version": None,
            "repo_content_version": None,
            "update_reasons": []
        }
        
        # Check for critical files (nuclear restore scenario)
        base_dir = self.config.get('config', {}).get('target_paths', {}).get('base_directory', '/var/www/homeserver')
        src_dir = os.path.join(base_dir, 'src')
        homeserver_json = os.path.join(src_dir, 'config', 'homeserver.json')
        
        if not os.path.exists(src_dir) or not os.path.exists(homeserver_json):
            log_message("Critical files missing - nuclear restore needed", "WARNING")
            update_details["update_reasons"].append("Critical files missing")
            return True, True, update_details
        
        # Schema version comparison
        local_schema = self.config.get("metadata", {}).get("schema_version", "0.0.0")
        repo_schema = local_schema  # Default fallback
        
        try:
            repo_index_path = os.path.join(temp_dir, "index.json")
            if os.path.exists(repo_index_path):
                with open(repo_index_path, 'r') as f:
                    repo_config = json.load(f)
                repo_schema = repo_config.get("metadata", {}).get("schema_version", "0.0.0")
        except Exception as e:
            log_message(f"Failed to read repository schema version: {e}", "WARNING")
        
        update_details["local_schema_version"] = local_schema
        update_details["repo_schema_version"] = repo_schema
        
        if compare_schema_versions(repo_schema, local_schema) > 0:
            update_details["schema_update_needed"] = True
            update_details["update_reasons"].append(f"Schema update: {local_schema} → {repo_schema}")
        
        # Content version comparison
        local_content = self._get_local_version()
        repo_content = self.git.get_repository_version(temp_dir)
        
        update_details["local_content_version"] = local_content
        update_details["repo_content_version"] = repo_content
        
        if repo_content and local_content and compare_schema_versions(repo_content, local_content) > 0:
            update_details["content_update_needed"] = True
            update_details["update_reasons"].append(f"Content update: {local_content} → {repo_content}")
        
        update_needed = update_details["schema_update_needed"] or update_details["content_update_needed"]
        
        if update_needed:
            log_message(f"Update needed: {', '.join(update_details['update_reasons'])}")
        else:
            log_message("No update needed - all versions current")
        
        return update_needed, False, update_details
    
    def _create_backup(self) -> bool:
        """Create a backup of the current website installation."""
        log_message("Creating website backup...")
        
        base_dir = self.config.get('config', {}).get('target_paths', {}).get('base_directory', '/var/www/homeserver')
        
        backup_files = [
            os.path.join(base_dir, 'src'),
            os.path.join(base_dir, 'backend'),
            os.path.join(base_dir, 'premium'),
            os.path.join(base_dir, 'public'),
            os.path.join(base_dir, 'main.py'),
            os.path.join(base_dir, 'config.py'),
            os.path.join(base_dir, 'package.json'),
            os.path.join(base_dir, 'requirements.txt'),
        ]
        
        # Filter to only existing files
        existing_files = [f for f in backup_files if os.path.exists(f)]
        
        if not existing_files:
            log_message("No files found to backup", "WARNING")
            return False
        
        backup_success = self.state_manager.backup_module_state(
            module_name="website",
            description=f"Pre-update backup {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            files=existing_files,
            services=["gunicorn.service"]
        )
        
        if backup_success:
            log_message("✓ Website backup created successfully")
        else:
            log_message("✗ Website backup creation failed", "ERROR")
        
        return backup_success
    
    def _restore_permissions(self) -> bool:
        """Restore website permissions using the PermissionManager."""
        log_message("Restoring website permissions...")
        
        base_dir = self.config.get('config', {}).get('target_paths', {}).get('base_directory', '/var/www/homeserver')
        
        # Define permission targets based on config
        targets = [
            PermissionTarget(
                path=base_dir,
                owner="www-data",
                group="www-data",
                mode=0o755,
                recursive=True
            )
        ]
        
        # Handle ramdisk permissions if it exists
        if os.path.exists("/mnt/ramdisk"):
            targets.append(PermissionTarget(
                path="/mnt/ramdisk",
                owner="root",
                group="ramdisk",
                mode=0o775,
                recursive=True
            ))
        
        success = self.permission_manager.set_permissions(targets)
        
        if success:
            log_message("✓ Website permissions restored successfully")
        else:
            log_message("⚠ Some permission restoration failed", "WARNING")
        
        return success
    
    def _update_module_versions(self, new_content_version: str = None) -> bool:
        """Update module versions in index.json."""
        try:
            if new_content_version:
                # Update the content version in our module's index.json
                if "metadata" not in self.config:
                    self.config["metadata"] = {}
                
                self.config["metadata"]["content_version"] = new_content_version
                
                with open(self.index_file, 'w') as f:
                    json.dump(self.config, f, indent=4)
                
                log_message(f"Updated module content version to: {new_content_version}")
            
            return True
            
        except Exception as e:
            log_message(f"Failed to update module versions: {e}", "ERROR")
            return False
    
    def _update_homeserver_json_metadata(self, new_version: str) -> bool:
        """Update the version and timestamp in homeserver.json."""
        try:
            base_dir = self.config.get('config', {}).get('target_paths', {}).get('base_directory', '/var/www/homeserver')
            homeserver_config_path = os.path.join(base_dir, "src", "config", "homeserver.json")
            
            if not os.path.exists(homeserver_config_path):
                log_message(f"Homeserver config not found at {homeserver_config_path}", "WARNING")
                return False
            
            with open(homeserver_config_path, 'r') as f:
                config_data = json.load(f)
            
            # Update version and timestamp
            current_date = datetime.now().strftime("%m-%d-%Y")
            
            if "global" not in config_data:
                config_data["global"] = {}
            if "version" not in config_data["global"]:
                config_data["global"]["version"] = {}
            
            config_data["global"]["version"]["version"] = new_version
            config_data["global"]["version"]["lastUpdated"] = current_date
            
            with open(homeserver_config_path, 'w') as f:
                json.dump(config_data, f, indent=4)
            
            log_message(f"Updated homeserver.json version to: {new_version} (date: {current_date})")
            return True
            
        except Exception as e:
            log_message(f"Failed to update homeserver.json metadata: {e}", "ERROR")
            return False
    
    def update(self) -> Dict[str, Any]:
        """
        Main update function that orchestrates the complete website update process.
        
        Returns:
            Dict containing update results with success status, update details, and any errors
        """
        start_time = time.time()
        
        log_message("="*60)
        log_message("STARTING WEBSITE UPDATE PROCESS")
        log_message("="*60)
        
        result = {
            "success": False,
            "updated": False,
            "message": "",
            "schema_updated": False,
            "content_updated": False,
            "error": None,
            "rollback_success": None,
            "duration": 0,
            "details": {}
        }
        
        temp_dir = None
        
        try:
            # Step 0: Always run maintenance tasks (agnostic of building)
            log_message("Step 0: Running maintenance tasks…")
            try:
                self.maintenance.update_browserslist()
            except Exception as maint_err:
                # Never fail the update due to maintenance tasks
                log_message(f"Maintenance task error (non-fatal): {maint_err}", "WARNING")

            # Step 1: Clone repository
            log_message("Step 1: Cloning repository...")
            temp_dir = self.git.clone_repository()
            if not temp_dir:
                raise WebsiteUpdateError("Failed to clone repository")
            
            # Step 2: Check if update is needed
            log_message("Step 2: Checking if update is needed...")
            update_needed, nuclear_restore, update_details = self._check_version_update_needed(temp_dir)
            result["details"] = update_details
            
            if not update_needed:
                result["success"] = True
                result["message"] = "No update needed - all versions current"
                log_message("✓ No update needed")
                return result
            
            # Step 3: Create backup
            log_message("Step 3: Creating backup...")
            if not self._create_backup():
                raise WebsiteUpdateError("Failed to create backup")
            
            # Step 4: Validate file operations
            log_message("Step 4: Validating file operations...")
            if not self.files.validate_file_operations(temp_dir):
                raise WebsiteUpdateError("File operation validation failed")
            
            # Step 5: Update files
            log_message("Step 5: Updating files...")
            if not self.files.update_components(temp_dir):
                raise WebsiteUpdateError("File update failed")
            
            # Step 6: Run build process
            log_message("Step 6: Running build process...")
            if not self.build.run_build_process():
                raise WebsiteUpdateError("Build process failed")
            
            # Step 7: Restore permissions
            log_message("Step 7: Restoring permissions...")
            self._restore_permissions()  # Don't fail on permission issues
            
            # Step 8: Update versions
            log_message("Step 8: Updating version metadata...")
            if update_details["content_update_needed"] and update_details["repo_content_version"]:
                self._update_homeserver_json_metadata(update_details["repo_content_version"])
                self._update_module_versions(update_details["repo_content_version"])
                result["content_updated"] = True
            
            if update_details["schema_update_needed"]:
                result["schema_updated"] = True
            
            # Success!
            result["success"] = True
            result["updated"] = True
            result["message"] = f"Website updated successfully ({', '.join(update_details['update_reasons'])})"
            
            duration = time.time() - start_time
            result["duration"] = duration
            
            log_message("="*60)
            log_message(f"✓ WEBSITE UPDATE COMPLETED SUCCESSFULLY ({duration:.1f}s)")
            log_message("="*60)
            
        except Exception as e:
            log_message(f"✗ Website update failed: {e}", "ERROR")
            result["error"] = str(e)
            result["message"] = f"Update failed: {e}"
            
            # Attempt rollback
            log_message("Attempting rollback...")
            try:
                rollback_success = self.state_manager.restore_module_state("website")
                result["rollback_success"] = rollback_success
                if rollback_success:
                    log_message("✓ Rollback completed successfully")
                    result["message"] += " (rollback successful)"
                else:
                    log_message("✗ Rollback failed", "ERROR")
                    result["message"] += " (rollback failed)"
            except Exception as rollback_error:
                log_message(f"✗ Rollback failed: {rollback_error}", "ERROR")
                result["rollback_success"] = False
                result["message"] += f" (rollback failed: {rollback_error})"
        
        finally:
            # Cleanup
            if temp_dir:
                self.git.cleanup_repository(temp_dir)
            
            duration = time.time() - start_time
            result["duration"] = duration
        
        return result


def main(args=None):
    """
    Main entry point for the website update module.
    
    Args:
        args: Optional command line arguments
    """
    log_message("Website update module started")
    
    # Lightweight check-only mode for orchestrator detection
    if args and isinstance(args, (list, tuple)) and ("--check" in args or "--check-only" in args):
        updater = WebsiteUpdater()
        temp_dir = None
        try:
            temp_dir = updater.git.clone_repository()
            if not temp_dir:
                return {
                    "success": False,
                    "update_available": False,
                    "error": "Failed to clone repository for check"
                }
            update_needed, nuclear_restore, details = updater._check_version_update_needed(temp_dir)
            return {
                "success": True,
                "update_available": bool(update_needed or nuclear_restore or details.get("schema_update_needed") or details.get("content_update_needed")),
                "nuclear_restore": nuclear_restore,
                "update_reasons": details.get("update_reasons", []),
                "local_schema_version": details.get("local_schema_version"),
                "repo_schema_version": details.get("repo_schema_version"),
                "local_content_version": details.get("local_content_version"),
                "repo_content_version": details.get("repo_content_version")
            }
        except Exception as e:
            return {
                "success": False,
                "update_available": False,
                "error": str(e)
            }
        finally:
            if temp_dir:
                try:
                    updater.git.cleanup_repository(temp_dir)
                except Exception:
                    pass

    try:
        updater = WebsiteUpdater()
        result = updater.update()
        
        if result["success"]:
            log_message("Website update module completed successfully")
            return result
        else:
            log_message(f"Website update module failed: {result['message']}", "ERROR")
            return result
            
    except Exception as e:
        log_message(f"Website update module crashed: {e}", "ERROR")
        return {
            "success": False,
            "updated": False,
            "message": f"Module crashed: {e}",
            "error": str(e),
            "rollback_success": None
        }


if __name__ == "__main__":
    import sys
    result = main(sys.argv[1:] if len(sys.argv) > 1 else None)
    sys.exit(0 if result["success"] else 1)
