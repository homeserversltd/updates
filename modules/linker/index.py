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
HOMESERVER Linker Update Module

Handles updating the HOMESERVER linker script suite from GitHub repository.
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
from updates.index import log_message
from updates.utils.state_manager import StateManager

class LinkerUpdateError(Exception):
    """Custom exception for linker update failures."""
    pass

class LinkerUpdater:
    """Git-based linker updater with StateManager integration and graceful failure handling."""
    
    def __init__(self, module_path: str = None):
        if module_path is None:
            module_path = os.path.dirname(os.path.abspath(__file__))
        
        self.module_path = Path(module_path)
        self.index_file = self.module_path / "index.json"
        self.config = self._load_config()
        self.state_manager = StateManager("/var/backups/linker")
        
    def _load_config(self) -> Dict[str, Any]:
        """Load the linker configuration from index.json."""
        try:
            with open(self.index_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            log_message(f"Failed to load linker config: {e}", "ERROR")
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
            temp_dir = None
            
            for component_name, component_config in components.items():
                if component_config.get('enabled', False):
                    target_path = component_config['target_path']
                    if os.path.exists(target_path):
                        if component_name == "library":
                            # For library component, create a temporary copy excluding venv
                            log_message(f"Creating temporary backup of library excluding venv directory")
                            temp_dir = tempfile.mkdtemp(prefix="linker_backup_")
                            temp_library_path = os.path.join(temp_dir, "linker_library")
                            
                            # Copy library excluding venv, __pycache__, etc.
                            shutil.copytree(
                                target_path, 
                                temp_library_path,
                                ignore=shutil.ignore_patterns('venv', '__pycache__', '*.pyc', '*.log', '.git')
                            )
                            backup_files.append(temp_library_path)
                        else:
                            # For other components, backup as-is
                            backup_files.append(target_path)
            
            if not backup_files:
                log_message("No files to backup")
                return True
            
            log_message(f"Backing up {len(backup_files)} linker components")
            backup_success = self.state_manager.backup_module_state(
                module_name="linker",
                description="Pre-linker-update backup",
                files=backup_files
            )
            
            # Clean up temporary directory
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
                log_message("Cleaned up temporary backup directory")
            
            if backup_success:
                log_message("Linker backup created successfully")
                return True
            else:
                log_message("Linker backup creation failed", "ERROR")
                return False
                
        except Exception as e:
            log_message(f"Backup failed: {e}", "ERROR")
            # Clean up temporary directory on error
            if 'temp_dir' in locals() and temp_dir and os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                except Exception:
                    pass
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
                
                # Handle special cases for different component types
                if component_name == "library":
                    # For the complete library, copy everything except .git and venv
                    if not os.path.exists(source_dir):
                        log_message(f"Source directory {source_dir} does not exist, skipping {component_name}", "WARNING")
                        continue
                    
                    # Remove existing target directory
                    if os.path.exists(target_path):
                        shutil.rmtree(target_path)
                    
                    # Ensure parent directory exists
                    os.makedirs(os.path.dirname(target_path), exist_ok=True)
                    
                    # Copy entire repository except .git and venv directories
                    shutil.copytree(source_dir, target_path, ignore=shutil.ignore_patterns('.git', 'venv', '__pycache__', '*.pyc'))
                    
                    # Set up virtual environment and install dependencies
                    self._setup_virtual_environment(target_path)
                    
                elif component_name == "symlink":
                    # Handle symlink creation - point to the linker executable in the library
                    source_executable = "/usr/local/lib/linker/linker"
                    
                    # Remove existing symlink/file
                    if os.path.exists(target_path) or os.path.islink(target_path):
                        os.remove(target_path)
                    
                    # Ensure parent directory exists
                    os.makedirs(os.path.dirname(target_path), exist_ok=True)
                    
                    # Create symlink
                    os.symlink(source_executable, target_path)
                    log_message(f"Created symlink: {target_path} → {source_executable}")
                
                log_message(f"Updated {component_name}: {source_path} → {target_path}")
                
            except Exception as e:
                log_message(f"Failed to update component {component_name}: {e}", "ERROR")
                return False
        
        log_message("All enabled components updated successfully")
        return True
    
    def _rollback_installation(self) -> None:
        """Rollback installation using StateManager."""
        log_message("Rolling back linker installation")
        
        try:
            restore_success = self.state_manager.restore_module_state("linker")
            if restore_success:
                log_message("Linker rollback completed successfully")
            else:
                log_message("Linker rollback failed", "ERROR")
        except Exception as e:
            log_message(f"Error during rollback: {e}", "ERROR")
    
    def _setup_virtual_environment(self, target_path: str) -> bool:
        """Set up virtual environment and install dependencies for the linker library."""
        try:
            venv_dir = os.path.join(target_path, "venv")
            requirements_file = os.path.join(target_path, "requirements.txt")
            setup_script = os.path.join(target_path, "setup_venv.sh")
            
            # Run the setup_venv.sh script if it exists
            if os.path.exists(setup_script):
                log_message("Running setup_venv.sh script")
                success = self._execute_command(["/bin/bash", setup_script], cwd=target_path)
                if success:
                    log_message("Virtual environment setup completed successfully")
                    return True
                else:
                    log_message("setup_venv.sh script failed, attempting manual setup", "WARNING")
            
            # Manual setup as fallback
            log_message("Setting up virtual environment manually")
            
            # Create virtual environment
            if not self._execute_command(["python3", "-m", "venv", venv_dir]):
                log_message("Failed to create virtual environment", "ERROR")
                return False
            
            # Install requirements if they exist
            if os.path.exists(requirements_file):
                pip_path = os.path.join(venv_dir, "bin", "pip")
                if not self._execute_command([pip_path, "install", "--upgrade", "pip"]):
                    log_message("Failed to upgrade pip", "WARNING")
                
                if not self._execute_command([pip_path, "install", "-r", requirements_file]):
                    log_message("Failed to install requirements", "ERROR")
                    return False
                
                log_message("Requirements installed successfully")
            else:
                log_message("No requirements.txt found, skipping dependency installation")
            
            return True
            
        except Exception as e:
            log_message(f"Virtual environment setup failed: {e}", "ERROR")
            return False
    
    def _cleanup_temp_directory(self, temp_dir: str) -> None:
        """Clean up temporary directory."""
        try:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
                log_message(f"Cleaned up temporary directory: {temp_dir}")
        except Exception as e:
            log_message(f"Failed to clean up temp directory: {e}", "WARNING")
    
    def update(self) -> Dict[str, Any]:
        """Perform the complete linker update process."""
        if not self.config['metadata'].get('enabled', True):
            log_message("Linker updater is disabled")
            return {"success": True, "message": "Linker updater disabled"}
        
        log_message("Starting linker update process")
        temp_dir = None
        
        try:
            # Step 1: Create backup
            if not self._backup_current_installation():
                return {
                    "success": False,
                    "error": "Backup creation failed",
                    "message": "Failed to create backup of current installation"
                }
            
            # Step 2: Clone repository
            temp_dir = self._clone_repository()
            if not temp_dir:
                return {
                    "success": False,
                    "error": "Repository clone failed",
                    "message": "Failed to clone GitHub repository"
                }
            
            # Step 3: Update components
            if not self._update_components(temp_dir):
                log_message("Component update failed, rolling back", "ERROR")
                self._rollback_installation()
                return {
                    "success": False,
                    "error": "Component update failed",
                    "message": "Failed to update linker components, rolled back to previous version"
                }
            
            log_message("Linker update completed successfully")
            return {
                "success": True,
                "message": "Linker updated successfully",
                "components_updated": len([c for c in self.config['config']['target_paths']['components'].values() if c.get('enabled', False)])
            }
            
        except Exception as e:
            log_message(f"Linker update failed: {e}", "ERROR")
            self._rollback_installation()
            return {
                "success": False,
                "error": str(e),
                "message": "Linker update encountered an unexpected error, rolled back to previous version"
            }
            
        finally:
            # Always cleanup temp directory
            if temp_dir:
                self._cleanup_temp_directory(temp_dir)

def main(args=None):
    """
    Main entry point for linker module.
    
    Args:
        args: List of arguments (supports '--check', '--version')
        
    Returns:
        dict: Status and results of the linker update operation
    """
    if args is None:
        args = []
    
    # CRITICAL: Ensure module is running latest schema version before execution
    module_dir = Path(__file__).parent
    from updates.utils.module_self_update import ensure_module_self_updated
    if not ensure_module_self_updated(module_dir):
        return {"success": False, "error": "Module self-update failed"}
    
    # Get module path
    module_path = os.path.dirname(os.path.abspath(__file__))
    
    try:
        updater = LinkerUpdater(module_path)
        
        if "--check" in args:
            config = updater.config
            components = config.get('config', {}).get('target_paths', {}).get('components', {})
            enabled_components = [name for name, comp in components.items() if comp.get('enabled', False)]
            
            log_message(f"Linker module status: {len(enabled_components)} enabled components")
            return {
                "success": True,
                "enabled_components": enabled_components,
                "total_components": len(components),
                "schema_version": config.get("metadata", {}).get("schema_version", "unknown")
            }
        
        elif "--version" in args:
            config = updater.config
            schema_version = config.get("metadata", {}).get("schema_version", "unknown")
            log_message(f"Linker module version: {schema_version}")
            return {
                "success": True,
                "schema_version": schema_version,
                "module": "linker"
            }
        
        else:
            # Perform linker update
            return updater.update()
            
    except Exception as e:
        log_message(f"Linker module failed: {e}", "ERROR")
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    import sys
    result = main(sys.argv[1:])
    if not result.get("success", False):
        sys.exit(1) 