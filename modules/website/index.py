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

"""
HOMESERVER Website Update Module

Handles updating the HOMESERVER web interface from GitHub repository.
Supports selective component updates and automatic rollback on failure.
"""

import os
import sys
import json
import shutil
import subprocess
import tempfile
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import requests
import time
from updates.index import log_message, compare_schema_versions
from updates.utils.state_manager import StateManager
from updates.utils.permissions import PermissionManager

class WebsiteUpdateError(Exception):
    """Custom exception for website update failures."""
    pass

def restore_website_permissions(config: Dict[str, Any]) -> bool:
    """
    Restore website permissions using PermissionManager for enabled components.
    
    Args:
        config: Module configuration containing components and permissions
        
    Returns:
        bool: True if permissions restored successfully, False otherwise
    """
    try:
        log_message("Restoring website permissions...")
        
        # Initialize PermissionManager
        permission_manager = PermissionManager()
        
        # Get components and permissions configuration
        components = config.get('config', {}).get('target_paths', {}).get('components', {})
        permissions = config.get('permissions', {})
        
        if not components:
            log_message("No components configuration found, skipping permission restoration")
            return True
        
        if not permissions:
            log_message("No permissions configuration found, skipping permission restoration")
            return True
        
        # Build targets from enabled components
        targets = []
        default_owner = permissions.get('owner', 'www-data')
        default_group = permissions.get('group', 'www-data')
        default_dir_mode = permissions.get('directory_mode', '755')
        default_file_mode = permissions.get('file_mode', '644')
        
        for component_name, component_config in components.items():
            if component_config.get('enabled', False):
                target_path = component_config['target_path']
                
                # Determine if this is a file or directory based on the path
                if target_path.endswith('.json') or '.' in os.path.basename(target_path):
                    # This is a file
                    mode = default_file_mode
                else:
                    # This is a directory
                    mode = default_dir_mode
                
                target = permission_manager.create_target(
                    path=target_path,
                    owner=default_owner,
                    group=default_group,
                    mode=mode,
                    recursive=True if not target_path.endswith('.json') else False
                )
                targets.append(target)
                log_message(f"Added permission target: {target_path} ({default_owner}:{default_group} {mode})")
        
        if not targets:
            log_message("No permission targets configured from enabled components")
            return True
        
        # Apply permissions
        success = permission_manager.apply_permissions(targets)
        
        if success:
            log_message(f"Successfully restored permissions for {len(targets)} website components")
            return True
        else:
            log_message("Failed to restore website permissions", "ERROR")
            return False
            
    except Exception as e:
        log_message(f"Error restoring website permissions: {e}", "ERROR")
        return False

class WebsiteUpdater:
    """Git-based website updater with StateManager integration and graceful failure handling."""
    
    def __init__(self, module_path: str = None):
        if module_path is None:
            module_path = os.path.dirname(os.path.abspath(__file__))
        
        self.module_path = Path(module_path)
        self.index_file = self.module_path / "index.json"
        self.config = self._load_config()
        self.state_manager = StateManager("/var/backups/website")
        
    def _load_config(self) -> Dict[str, Any]:
        """Load the website configuration from index.json."""
        try:
            with open(self.index_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            log_message(f"Failed to load website config: {e}", "ERROR")
            return {}
    
    def _execute_command(self, command: List[str], cwd: str = None, timeout: int = 300) -> bool:
        """Execute a command and return success status."""
        try:
            log_message(f"Running: {' '.join(command)}")
            result = subprocess.run(
                command,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            if result.returncode != 0:
                log_message(f"Command failed: {' '.join(command)}", "ERROR")
                log_message(f"Error output: {result.stderr}", "ERROR")
                return False
            
            if result.stdout:
                log_message(f"Command output: {result.stdout}")
            
            log_message(f"Command succeeded: {' '.join(command)}")
            return True
            
        except subprocess.TimeoutExpired:
            log_message(f"Command timed out: {' '.join(command)}", "ERROR")
            return False
        except Exception as e:
            log_message(f"Command execution failed: {' '.join(command)} - {e}", "ERROR")
            return False
    
    def _clone_repository(self) -> Optional[str]:
        """Clone the GitHub repository to temporary directory."""
        repo_config = self.config['config']['repository']
        temp_dir = repo_config['temp_directory']
        
        try:
            # Clean up existing temp directory
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
                log_message(f"Cleaned up existing temp directory: {temp_dir}")
            
            # Clone repository
            clone_success = self._execute_command([
                'git', 'clone', 
                '--branch', repo_config['branch'],
                '--depth', '1',  # Shallow clone for faster download
                repo_config['url'],
                temp_dir
            ])
            
            if not clone_success:
                log_message("Failed to clone repository", "ERROR")
                return None
            
            log_message(f"Successfully cloned repository to {temp_dir}")
            return temp_dir
            
        except Exception as e:
            log_message(f"Repository cloning failed: {e}", "ERROR")
            return None
    
    def _backup_current_installation(self) -> bool:
        """Create backup of current installation using StateManager."""
        try:
            # Collect all target paths for backup
            components = self.config['config']['target_paths']['components']
            backup_files = []
            
            for component_name, component_config in components.items():
                if component_config.get('enabled', False):
                    target_path = component_config['target_path']
                    if os.path.exists(target_path):
                        backup_files.append(target_path)
            
            # Note: package-lock.json and node_modules are not backed up as they are generated artifacts
            
            if not backup_files:
                log_message("No files to backup")
                return True
            
            log_message(f"Backing up {len(backup_files)} website components")
            backup_success = self.state_manager.backup_module_state(
                module_name="website",
                description="Pre-website-update backup",
                files=backup_files
            )
            
            if backup_success:
                log_message("Website backup created successfully")
                return True
            else:
                log_message("Website backup creation failed", "ERROR")
                return False
                
        except Exception as e:
            log_message(f"Backup failed: {e}", "ERROR")
            return False
    
    def _update_components(self, source_dir: str) -> bool:
        """Update all enabled components from the cloned repository."""
        components = self.config['config']['target_paths']['components']
        
        for component_name, component_config in components.items():
            if not component_config.get('enabled', False):
                log_message(f"Component {component_name} is disabled, skipping")
                continue
            
            try:
                source_path = os.path.join(source_dir, component_config['source_path'])
                target_path = component_config['target_path']
                
                if not os.path.exists(source_path):
                    log_message(f"Source path {source_path} does not exist, skipping {component_name}", "WARNING")
                    continue
                
                # Remove existing target if it's a directory
                if os.path.exists(target_path) and os.path.isdir(target_path):
                    shutil.rmtree(target_path)
                elif os.path.exists(target_path):
                    os.remove(target_path)
                
                # Ensure parent directory exists
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                
                # Copy new content
                if os.path.isdir(source_path):
                    shutil.copytree(source_path, target_path)
                else:
                    shutil.copy2(source_path, target_path)
                
                log_message(f"Updated {component_name}: {source_path} → {target_path}")
                
            except Exception as e:
                log_message(f"Failed to update component {component_name}: {e}", "ERROR")
                return False
        
        log_message("All enabled components updated successfully")
        return True
    
    def _run_build_process(self) -> bool:
        """Run the npm build process and restart services."""
        base_dir = self.config['config']['target_paths']['base_directory']
        
        try:
            # Stop homeserver service
            log_message("Stopping homeserver service")
            if not self._execute_command(['systemctl', 'stop', 'homeserver.service']):
                log_message("Failed to stop homeserver service", "WARNING")
            
            # Run npm install
            log_message("Running npm install")
            if not self._execute_command(['npm', 'install'], cwd=base_dir, timeout=600):
                log_message("npm install failed", "ERROR")
                return False
            
            # Run npm build
            log_message("Running npm build")
            if not self._execute_command(['npm', 'run', 'build'], cwd=base_dir, timeout=600):
                log_message("npm build failed", "ERROR")
                return False
            
            # Restore permissions after build process
            log_message("Restoring permissions after build process")
            if not restore_website_permissions(self.config):
                log_message("Failed to restore permissions after build", "WARNING")
                # Don't fail the entire process for permission issues
            
            # Start homeserver service
            log_message("Starting homeserver service")
            if not self._execute_command(['systemctl', 'start', 'homeserver.service']):
                log_message("Failed to start homeserver service", "ERROR")
                return False
            
            # Check if homeserver is active
            log_message("Checking homeserver service status")
            if not self._execute_command(['systemctl', 'is-active', 'homeserver.service']):
                log_message("homeserver service is not active after restart", "ERROR")
                return False
            
            # Restart gunicorn service
            log_message("Restarting gunicorn service")
            if not self._execute_command(['systemctl', 'restart', 'gunicorn.service']):
                log_message("Failed to restart gunicorn service", "ERROR")
                return False
            
            # Check if gunicorn is active
            log_message("Checking gunicorn service status")
            if not self._execute_command(['systemctl', 'is-active', 'gunicorn.service']):
                log_message("gunicorn service is not active after restart", "ERROR")
                return False
            
            log_message("Build process and service restarts completed successfully")
            return True
            
        except Exception as e:
            log_message(f"Build process failed: {e}", "ERROR")
            return False
    
    def _rollback_installation(self) -> None:
        """Rollback installation using StateManager."""
        log_message("Rolling back website installation")
        
        try:
            restore_success = self.state_manager.restore_module_state("website")
            if restore_success:
                log_message("Website rollback completed successfully")
                
                # Restore permissions after rollback
                log_message("Restoring permissions after rollback")
                restore_website_permissions(self.config)
                
                # Restart services after rollback
                base_dir = self.config['config']['target_paths']['base_directory']
                log_message("Restarting services after rollback")
                
                self._execute_command(['systemctl', 'restart', 'homeserver.service'])
                self._execute_command(['systemctl', 'restart', 'gunicorn.service'])
                
            else:
                log_message("Website rollback failed", "ERROR")
        except Exception as e:
            log_message(f"Error during rollback: {e}", "ERROR")
    
    def _get_local_version(self) -> Optional[str]:
        """Get the current local version from homeserver.json."""
        try:
            local_config_path = "/var/www/homeserver/src/config/homeserver.json"
            if not os.path.exists(local_config_path):
                log_message("Local homeserver.json not found", "WARNING")
                return None
            
            with open(local_config_path, 'r') as f:
                config = json.load(f)
            
            version = config.get('global', {}).get('version', {}).get('version')
            if version:
                log_message(f"Local version: {version}")
                return version
            else:
                log_message("No version found in local homeserver.json", "WARNING")
                return None
                
        except Exception as e:
            log_message(f"Failed to read local version: {e}", "ERROR")
            return None
    
    def _get_repository_version(self, temp_dir: str) -> Optional[str]:
        """Get the version from the repository's homeserver.json."""
        try:
            repo_config_path = os.path.join(temp_dir, "src", "config", "homeserver.json")
            if not os.path.exists(repo_config_path):
                log_message("Repository homeserver.json not found", "WARNING")
                return None
            
            with open(repo_config_path, 'r') as f:
                config = json.load(f)
            
            version = config.get('global', {}).get('version', {}).get('version')
            if version:
                log_message(f"Repository version: {version}")
                return version
            else:
                log_message("No version found in repository homeserver.json", "WARNING")
                return None
                
        except Exception as e:
            log_message(f"Failed to read repository version: {e}", "ERROR")
            return None
    
    def _check_version_update_needed(self, temp_dir: str) -> bool:
        """Check if an update is needed by comparing actual website versions."""
        try:
            # Get the actual versions from homeserver.json files
            local_version = self._get_local_version()
            repo_version = self._get_repository_version(temp_dir)
            
            log_message(f"Version comparison: local={local_version}, repo={repo_version}")
            
            if not local_version or not repo_version:
                log_message("Could not determine versions, skipping update", "WARNING")
                return False
            
            # Compare versions using semantic versioning
            from updates import compare_schema_versions
            
            if compare_schema_versions(repo_version, local_version) > 0:
                log_message(f"Update needed: {local_version} → {repo_version}")
                return True
            else:
                log_message(f"Website is up to date: {local_version}")
                return False
                
        except Exception as e:
            log_message(f"Error checking version update: {e}", "ERROR")
            return False
    
    def _cleanup_temp_directory(self, temp_dir: str) -> None:
        """Clean up temporary directory."""
        try:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
                log_message(f"Cleaned up temporary directory: {temp_dir}")
        except Exception as e:
            log_message(f"Failed to clean up temp directory: {e}", "WARNING")
    
    def _update_module_content_version(self, new_version: str) -> bool:
        """Update the module's content_version to match the newly installed website version."""
        try:
            # Read current module config
            with open(self.index_file, 'r') as f:
                config = json.load(f)
            
            # Update the content_version in metadata
            if "metadata" not in config:
                config["metadata"] = {}
            
            old_version = config["metadata"].get("content_version", "unknown")
            config["metadata"]["content_version"] = new_version
            
            # Write updated config back to file
            with open(self.index_file, 'w') as f:
                json.dump(config, f, indent=4)
            
            log_message(f"Updated module content_version: {old_version} → {new_version}")
            return True
            
        except Exception as e:
            log_message(f"Failed to update module content_version: {e}", "ERROR")
            return False
    
    def update(self) -> Dict[str, Any]:
        """Perform the complete website update process with version checking."""
        if not self.config['metadata'].get('enabled', True):
            log_message("Website updater is disabled")
            return {"success": True, "message": "Website updater disabled"}
        
        log_message("Starting website update process")
        temp_dir = None
        
        try:
            # Step 1: Clone repository first to check versions
            temp_dir = self._clone_repository()
            if not temp_dir:
                return {
                    "success": False,
                    "error": "Repository clone failed",
                    "message": "Failed to clone GitHub repository"
                }
            
            # Step 2: Check if update is needed based on version comparison
            if not self._check_version_update_needed(temp_dir):
                log_message("No update needed - versions are equal or local is newer")
                return {
                    "success": True,
                    "message": "No update needed - website is already up to date",
                    "update_performed": False
                }
            
            # Step 3: Create backup before proceeding with update
            if not self._backup_current_installation():
                return {
                    "success": False,
                    "error": "Backup creation failed",
                    "message": "Failed to create backup of current installation"
                }
            
            # Step 4: Update components
            if not self._update_components(temp_dir):
                log_message("Component update failed, rolling back", "ERROR")
                self._rollback_installation()
                return {
                    "success": False,
                    "error": "Component update failed",
                    "message": "Failed to update website components, rolled back to previous version"
                }
            
            # Step 5: Run build process and restart services
            if not self._run_build_process():
                log_message("Build process failed, rolling back", "ERROR")
                self._rollback_installation()
                return {
                    "success": False,
                    "error": "Build process failed",
                    "message": "npm build or service restart failed, rolled back to previous version"
                }
            
            # Get version information for success message
            local_version = self._get_local_version()
            repo_version = self._get_repository_version(temp_dir)
            
            # Update the module's content_version to match the newly installed version
            if repo_version:
                self._update_module_content_version(repo_version)
            
            log_message("Website update completed successfully")
            return {
                "success": True,
                "message": f"Website updated successfully from {local_version} to {repo_version}",
                "components_updated": len([c for c in self.config['config']['target_paths']['components'].values() if c.get('enabled', False)]),
                "update_performed": True,
                "old_version": local_version,
                "new_version": repo_version
            }
            
        except Exception as e:
            log_message(f"Website update failed: {e}", "ERROR")
            if temp_dir:  # Only rollback if we had started the update process
                self._rollback_installation()
            return {
                "success": False,
                "error": str(e),
                "message": "Website update encountered an unexpected error, rolled back to previous version"
            }
            
        finally:
            # Always cleanup temp directory
            if temp_dir:
                self._cleanup_temp_directory(temp_dir)

def main(args=None):
    """
    Main entry point for website module.
    
    Args:
        args: List of arguments (supports '--check', '--version', '--fix-permissions')
        
    Returns:
        dict: Status and results of the website update operation
    """
    if args is None:
        args = []
    
    # Get module path
    module_path = os.path.dirname(os.path.abspath(__file__))
    
    try:
        updater = WebsiteUpdater(module_path)
        
        if "--fix-permissions" in args:
            log_message("Fixing website permissions...")
            success = restore_website_permissions(updater.config)
            return {
                "success": success,
                "message": "Website permissions fixed" if success else "Failed to fix website permissions"
            }
        
        elif "--check" in args:
            config = updater.config
            components = config.get('config', {}).get('target_paths', {}).get('components', {})
            enabled_components = [name for name, comp in components.items() if comp.get('enabled', False)]
            
            # Use the new multi-level version checking system
            from updates import check_multi_level_version_update
            
            temp_dir = None
            update_status = {
                "update_needed": False,
                "schema_versions": {"local": None, "repo": None},
                "content_versions": {"local": None, "repo": None},
                "update_reason": []
            }
            
            try:
                temp_dir = updater._clone_repository()
                if temp_dir:
                    # Get module paths
                    repo_module_path = temp_dir
                    local_module_path = "/usr/local/lib/updates/modules/website"
                    
                    # Check for updates using the enhanced system
                    update_status = check_multi_level_version_update(config, repo_module_path, local_module_path)
            except Exception as e:
                log_message(f"Failed to check for updates: {e}", "WARNING")
            finally:
                if temp_dir:
                    updater._cleanup_temp_directory(temp_dir)
            
            log_message(f"Website module status: {len(enabled_components)} enabled components")
            if update_status["update_needed"]:
                reasons = ", ".join(update_status["update_reason"])
                log_message(f"Update available: {reasons}")
            else:
                schema_local = update_status["schema_versions"]["local"] or "0.0.0"
                content_local = update_status["content_versions"]["local"] or "unknown"
                log_message(f"Website is up to date: schema {schema_local}, content {content_local}")
            
            return {
                "success": True,
                "enabled_components": enabled_components,
                "total_components": len(components),
                "schema_version": config.get("metadata", {}).get("schema_version", "unknown"),
                "content_version": config.get("metadata", {}).get("content_version", "unknown"),
                "update_available": update_status["update_needed"],
                "schema_versions": update_status["schema_versions"],
                "content_versions": update_status["content_versions"],
                "update_reasons": update_status["update_reason"]
            }
        
        elif "--version" in args:
            config = updater.config
            schema_version = config.get("metadata", {}).get("schema_version", "unknown")
            log_message(f"Website module version: {schema_version}")
            return {
                "success": True,
                "schema_version": schema_version,
                "module": "website"
            }
        
        else:
            # Perform website update
            return updater.update()
            
    except Exception as e:
        log_message(f"Website module failed: {e}", "ERROR")
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    import sys
    result = main(sys.argv[1:])
    if not result.get("success", False):
        sys.exit(1)
