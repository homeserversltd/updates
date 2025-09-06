"""
HOMESERVER Website Update Components
Copyright (C) 2024 HOMESERVER LLC

Website Updater Component

Handles full website updates including:
- Comprehensive backup of everything
- Git clone clobber of src/backend
- Premium tab restoration via premium installer
- Build process and service restart
- Rollback capabilities

This component is designed for full website updates where git clone will clobber
the entire src/backend, requiring premium tab reinstallation.
"""

import os
import time
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime
from updates.index import log_message
import subprocess

from .backup_manager import BackupManager
from .git_operations import GitOperations
from .file_operations import FileOperations
from .build_manager import BuildManager
# MaintenanceManager removed - consolidated into root maintenance.py
from .premium_tab_checker import PremiumTabChecker


class WebsiteUpdater:
    """Handles comprehensive website updates with premium tab restoration."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.base_dir = config.get('config', {}).get('target_paths', {}).get('base_directory', '/var/www/homeserver')
        
        # Initialize all required components
        self.backup_manager = BackupManager(config)
        self.git = GitOperations(config)
        self.files = FileOperations(config)
        self.build = BuildManager(config)
        self.premium_tab_checker = PremiumTabChecker(config)
        
        # Premium installer path for tab restoration
        self.premium_installer_path = os.path.join(self.base_dir, 'premium', 'installer.py')
    
    def update(self) -> Dict[str, Any]:
        """
        Perform comprehensive website update with premium tab restoration.
        
        Returns:
            Dict containing update results with success status and details
        """
        start_time = time.time()
        
        log_message("="*60)
        log_message("STARTING COMPREHENSIVE WEBSITE UPDATE")
        log_message("="*60)
        
        result = {
            "success": False,
            "updated": False,
            "message": "",
            "content_updated": False,
            "premium_tabs_restored": False,
            "error": None,
            "rollback_success": None,
            "duration": 0,
            "details": {}
        }
        
        temp_dir = None
        
        try:
            # Step 0: Maintenance tasks now handled by root maintenance.py
            log_message("Step 0: Maintenance tasks handled by root maintenance system")
            
            # Step 1: Clone repository
            log_message("Step 1: Cloning repository...")
            temp_dir = self.git.clone_repository()
            if not temp_dir:
                raise Exception("Failed to clone repository")
            
            # Step 2: Check if update is needed
            log_message("Step 2: Checking if update is needed...")
            update_needed, nuclear_restore, update_details = self._check_version_update_needed(temp_dir)
            result["details"] = update_details
            
            if not update_needed:
                result["success"] = True
                result["message"] = "No update needed - all versions current"
                log_message("✓ No update needed")
                return result
            
            # Step 2.5: Handle missing critical files (just do normal update)
            if nuclear_restore:
                log_message("🚨 CRITICAL FILES MISSING - Proceeding with normal update process...")
                log_message("🚨 This will restore the website from GitHub and preserve any existing config")
            
            # Step 3: Create comprehensive backup (everything)
            log_message("Step 3: Creating comprehensive backup...")
            if not self.backup_manager.backup_for_website_update():
                raise Exception("Failed to create comprehensive backup")
            
            # Step 4: Capture premium tab state before clobbering
            log_message("Step 4: Capturing premium tab state...")
            premium_tab_state = self._capture_premium_tab_state()
            if not premium_tab_state:
                log_message("⚠ Warning: Could not capture premium tab state", "WARNING")
            
            # Step 4.5: Capture and backup user customizations (themes, configs) before clobbering
            log_message("Step 4.5: Capturing and backing up user customizations...")
            user_customizations = self._capture_and_backup_user_customizations()
            if not user_customizations:
                log_message("⚠ Warning: Could not capture user customizations", "WARNING")
            
            # Step 5: Validate file operations
            log_message("Step 5: Validating file operations...")
            if not self.files.validate_file_operations(temp_dir):
                raise Exception("File operation validation failed")
            
            # Step 5.5: Stop gunicorn service before file operations
            log_message("Step 5.5: Stopping gunicorn service to release file handles...")
            if not self._stop_gunicorn_service():
                log_message("⚠ Warning: Failed to stop gunicorn service", "WARNING")
                # Don't fail the update, but log the warning
            
            # Step 6: Update files (this clobbers src/backend)
            log_message("Step 6: Updating website files (clobbering src/backend)...")
            if not self.files.update_components(temp_dir):
                raise Exception("File update failed")
            
            # Step 6.5: Restore user customizations (themes, configs)
            log_message("Step 6.5: Restoring user customizations...")
            if user_customizations:
                customization_restoration_success = self._restore_user_customizations(user_customizations)
                if not customization_restoration_success:
                    log_message("⚠ Warning: User customization restoration failed", "WARNING")
            else:
                log_message("⚠ No user customizations to restore", "WARNING")
            
            # Step 7: Restore premium tabs using premium installer
            log_message("Step 7: Restoring premium tabs...")
            if premium_tab_state:
                tab_restoration_success = self._restore_premium_tabs(premium_tab_state)
                result["premium_tabs_restored"] = tab_restoration_success
                if not tab_restoration_success:
                    log_message("⚠ Warning: Premium tab restoration failed", "WARNING")
            else:
                log_message("⚠ No premium tab state to restore", "WARNING")
            
            # Step 8: Restore permissions before build process
            log_message("Step 8: Restoring permissions before build...")
            self._restore_permissions()  # Don't fail on permission issues
            
            # Step 9: Run build process (now includes restored premium tabs)
            log_message("Step 9: Running build process with premium tabs...")
            if not self.build.run_build_process():
                raise Exception("Build process failed")
            
            # Step 10: Update version metadata
            log_message("Step 10: Updating version metadata...")
            if update_details["content_update_needed"] and update_details["repo_content_version"]:
                self._update_homeserver_json_metadata(update_details["repo_content_version"])
                self._update_module_versions(update_details["repo_content_version"])
                result["content_updated"] = True
            

            
            # Success!
            result["success"] = True
            result["updated"] = True
            result["message"] = f"Website updated successfully ({', '.join(update_details['update_reasons'])})"
            
            duration = time.time() - start_time
            result["duration"] = duration
            
            log_message("="*60)
            log_message(f"✓ COMPREHENSIVE WEBSITE UPDATE COMPLETED SUCCESSFULLY ({duration:.1f}s)")
            log_message("="*60)
            
        except Exception as e:
            log_message(f"✗ Website update failed: {e}", "ERROR")
            result["error"] = str(e)
            result["message"] = f"Update failed: {e}"
            
            # Attempt rollback using StateManager
            log_message("Attempting rollback using StateManager...")
            try:
                rollback_success = self.backup_manager.state_manager.restore_module_state_with_forced_service_start("website")
                result["rollback_success"] = rollback_success
                if rollback_success:
                    log_message("✓ Rollback successful using StateManager")
                    result["message"] += " (rollback successful)"
                else:
                    log_message("✗ Rollback failed using StateManager", "ERROR")
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
    
    
    def _check_version_update_needed(self, temp_dir: str) -> Tuple[bool, bool, Dict[str, Any]]:
        """
        Check if an update is needed by comparing content versions only.
        
        Schema version checking is the orchestrator's responsibility, not the module's.
        This method only checks if the website content needs updating.
        
        Returns:
            Tuple[bool, bool, Dict]: (update_needed, nuclear_restore_needed, update_details)
        """
        update_details = {
            "content_update_needed": False,
            "local_content_version": None,
            "repo_content_version": None,
            "update_reasons": [],
            "premium_tab_updates": []
        }
        
        # Check for critical files (nuclear restore scenario)
        src_dir = os.path.join(self.base_dir, 'src')
        homeserver_json = os.path.join(src_dir, 'config', 'homeserver.json')
        
        if not os.path.exists(src_dir) or not os.path.exists(homeserver_json):
            log_message("Critical files missing - nuclear restore needed", "WARNING")
            update_details["update_reasons"].append("Critical files missing")
            return True, True, update_details
        
        # Schema version checking is NOT the module's job - orchestrator handles this
        # The orchestrator has already determined if this module needs updating
        
        # Content version comparison (this is the module's business logic)
        local_content = self._get_local_version()
        repo_content = self.git.get_repository_version(temp_dir)
        
        update_details["local_content_version"] = local_content
        update_details["repo_content_version"] = repo_content
        
        # Check if content update is needed
        if repo_content and local_content:
            # Simple string comparison for content versions
            if repo_content != local_content:
                update_details["content_update_needed"] = True
                update_details["update_reasons"].append(f"Content update: {local_content} → {repo_content}")
        
        # Check premium tab updates
        log_message("Checking premium tabs for updates...")
        premium_tab_updates = self.premium_tab_checker.check_all_premium_tabs()
        update_details["premium_tab_updates"] = premium_tab_updates
        
        # Generate premium tab update summary
        if premium_tab_updates:
            update_summary = self.premium_tab_checker.get_update_summary(premium_tab_updates)
            log_message(f"Premium tab status: {update_summary}")
        
        # Determine if update is actually needed based on content version comparison only
        # Schema version checking is the orchestrator's responsibility - we only check content
        update_needed = update_details["content_update_needed"]
        
        if update_needed:
            log_message(f"Update needed: {', '.join(update_details['update_reasons'])}")
        else:
            log_message("No update needed - all versions current")
        
        return update_needed, False, update_details
    
    def _get_local_version(self) -> Optional[str]:
        """Get the local version from homeserver.json."""
        try:
            # Hardcoded version file and path
            version_file = 'src/config/homeserver.json'
            version_path_components = 'global.version.version'.split('.')
            
            local_config_path = os.path.join(self.base_dir, version_file)
            
            if not os.path.exists(local_config_path):
                log_message(f"Local homeserver.json not found at {local_config_path}", "WARNING")
                return None
            
            import json
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
    
    def _capture_premium_tab_state(self) -> Optional[Dict[str, Any]]:
        """
        Capture current premium tab installation state before clobbering.
        
        Returns:
            Dict containing premium tab state, or None if failed
        """
        try:
            log_message("Capturing premium tab state...")
            
            # Use the premium installer to get the actual installed tabs
            # This is the correct way - don't just scan the premium directory
            installed_tabs = []
            
            if os.path.exists(self.premium_installer_path):
                try:
                    import subprocess
                    
                    # Run: python3 installer.py list --installed
                    cmd = [
                        "python3", 
                        self.premium_installer_path, 
                        "list", 
                        "--installed"
                    ]
                    
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        cwd=os.path.dirname(self.premium_installer_path)
                    )
                    
                    if result.returncode == 0:
                        # Parse the output to extract installed tab names
                        lines = result.stdout.strip().split('\n')
                        for line in lines:
                            line = line.strip()
                            if line.startswith('[INSTALLED]'):
                                # Format: "[INSTALLED] tabName (v1.0.0)"
                                # Extract tab name from between [INSTALLED] and (v...)
                                parts = line.split(' ')
                                if len(parts) >= 2:
                                    tab_name = parts[1]  # Get the tab name after [INSTALLED]
                                    installed_tabs.append({
                                        "name": tab_name,
                                        "version": "unknown",  # Could parse version if needed
                                        "path": os.path.join(self.base_dir, 'premium', tab_name)
                                    })
                        
                        log_message(f"✓ Found {len(installed_tabs)} actually installed premium tabs via installer")
                    else:
                        log_message(f"Warning: Installer list --installed failed, falling back to directory scan", "WARNING")
                        # Fallback to old method if installer fails
                        installed_tabs = self._fallback_capture_premium_tab_state()
                        
                except Exception as e:
                    log_message(f"Warning: Exception running installer list --installed, falling back to directory scan: {e}", "WARNING")
                    # Fallback to old method if installer fails
                    installed_tabs = self._fallback_capture_premium_tab_state()
            else:
                log_message("Warning: Premium installer not found, falling back to directory scan", "WARNING")
                # Fallback to old method if installer not found
                installed_tabs = self._fallback_capture_premium_tab_state()
            
            state = {
                "timestamp": datetime.now().isoformat(),
                "installed_tabs": installed_tabs,
                "total_tabs": len(installed_tabs)
            }
            
            log_message(f"✓ Captured state for {len(installed_tabs)} premium tabs")
            return state
            
        except Exception as e:
            log_message(f"✗ Failed to capture premium tab state: {e}", "ERROR")
            return None
    
    def _fallback_capture_premium_tab_state(self) -> List[Dict[str, Any]]:
        """
        Fallback method to capture premium tab state by scanning directory.
        This is the old method that incorrectly assumed all tabs in premium/ were installed.
        """
        installed_tabs = []
        premium_dir = os.path.join(self.base_dir, 'premium')
        
        if os.path.exists(premium_dir):
            for item in os.listdir(premium_dir):
                item_path = os.path.join(premium_dir, item)
                tab_index_path = os.path.join(item_path, 'index.json')
                
                if os.path.isdir(item_path) and os.path.exists(tab_index_path):
                    try:
                        import json
                        with open(tab_index_path, 'r') as f:
                            tab_config = json.load(f)
                        
                        installed_tabs.append({
                            "name": item,
                            "version": tab_config.get("version", "unknown"),
                            "path": item_path
                        })
                    except Exception as e:
                        log_message(f"Warning: Could not read tab config for {item}: {e}", "WARNING")
        
        return installed_tabs
    
    
    def _capture_directory_structure(self, directory_path: str) -> Dict[str, Any]:
        """
        Capture the complete structure and content of a directory.
        
        Args:
            directory_path: Path to directory to capture
            
        Returns:
            Dict containing directory structure and file contents
        """
        try:
            structure = {
                "type": "directory",
                "path": directory_path,
                "contents": {}
            }
            
            for item in os.listdir(directory_path):
                item_path = os.path.join(directory_path, item)
                
                if os.path.isfile(item_path):
                    # Capture file content
                    try:
                        with open(item_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                        
                        structure["contents"][item] = {
                            "type": "file",
                            "path": item_path,
                            "content": content,
                            "size": len(content)
                        }
                    except Exception as e:
                        log_message(f"Warning: Could not read file {item_path}: {e}", "WARNING")
                        structure["contents"][item] = {
                            "type": "file",
                            "path": item_path,
                            "error": str(e)
                        }
                        
                elif os.path.isdir(item_path):
                    # Recursively capture subdirectory
                    structure["contents"][item] = self._capture_directory_structure(item_path)
            
            return structure
            
        except Exception as e:
            log_message(f"Error capturing directory {directory_path}: {e}", "ERROR")
            return {"type": "directory", "path": directory_path, "error": str(e)}
    
    def _restore_premium_tabs(self, tab_state: Dict[str, Any]) -> bool:
        """
        Restore premium tabs using the premium installer.
        
        Args:
            tab_state: Premium tab state captured before update
            
        Returns:
            bool: True if restoration successful, False otherwise
        """
        try:
            if not os.path.exists(self.premium_installer_path):
                log_message("Premium installer not found, cannot restore tabs", "WARNING")
                return False
            
            installed_tabs = tab_state.get("installed_tabs", [])
            if not installed_tabs:
                log_message("No premium tabs to restore")
                return True
            
            log_message(f"Restoring {len(installed_tabs)} premium tabs...")
            
            # Use premium installer to install tabs (not reinstall)
            # Since website update clobbers entire backend/src, we need to install all tabs
            tab_names = []
            for tab_info in installed_tabs:
                tab_name = tab_info["name"]
                # Check if premium directory exists for this tab
                tab_path = os.path.join(self.base_dir, 'premium', tab_name)
                if os.path.exists(tab_path):
                    tab_names.append(tab_name)
                else:
                    log_message(f"⚠ Warning: Premium directory not found for {tab_name}: {tab_path}")
            
            if not tab_names:
                log_message("No valid premium tabs found")
                return False
            
            # Use the smart install command that automatically handles single vs multiple tabs
            log_message(f"Installing {len(tab_names)} tabs using smart install: {', '.join(tab_names)}")
            success = self._run_premium_installer_install(tab_names)
            if success:
                log_message(f"✓ Successfully restored {len(tab_names)} tabs")
            else:
                log_message(f"✗ Failed to restore some tabs")
                return False
            
            log_message("✓ Premium tab restoration completed")
            return True
            
        except Exception as e:
            log_message(f"✗ Premium tab restoration failed: {e}", "ERROR")
            return False
    
    def _run_premium_installer_install(self, tab_names: List[str]) -> bool:
        """
        Run premium installer install command for tabs.
        
        Args:
            tab_names: List of tab names to install
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            import subprocess
            
            # Run the premium installer install command with tab names
            cmd = [
                "python3", 
                self.premium_installer_path, 
                "install"
            ] + tab_names
            
            log_message(f"Running: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=os.path.dirname(self.premium_installer_path)
            )
            
            if result.returncode == 0:
                log_message(f"✓ Premium installer install successful for {len(tab_names)} tabs: {', '.join(tab_names)}")
                return True
            else:
                log_message(f"✗ Premium installer install failed")
                log_message(f"STDOUT: {result.stdout}")
                log_message(f"STDERR: {result.stderr}")
                return False
                
        except Exception as e:
            log_message(f"✗ Exception running premium installer install: {e}", "ERROR")
            return False
    
    def _restore_user_customizations(self, customizations: Dict[str, Any]) -> bool:
        """
        Restore user customizations after file update.
        
        Args:
            customizations: User customization state captured before update
            
        Returns:
            bool: True if restoration successful, False otherwise
        """
        try:
            if not customizations:
                log_message("No user customizations to restore")
                return True
            
            log_message("Restoring user customizations...")
            
            # Restore custom themes
            themes_restored = 0
            themes_failed = 0
            
            for theme_name, theme_data in customizations.get("themes", {}).items():
                try:
                    theme_path = theme_data["path"]
                    
                    # Remove any repository version that might have been copied
                    if os.path.exists(theme_path):
                        import shutil
                        shutil.rmtree(theme_path)
                    
                    # Restore user theme from captured data
                    if self._restore_directory_structure(theme_path, theme_data["files"]):
                        log_message(f"✓ Restored user theme: {theme_name}")
                        themes_restored += 1
                    else:
                        log_message(f"✗ Failed to restore theme: {theme_name}")
                        themes_failed += 1
                        
                except Exception as e:
                    log_message(f"✗ Exception restoring theme {theme_name}: {e}", "ERROR")
                    themes_failed += 1
            
            # Restore other user configs
            configs_restored = 0
            configs_failed = 0
            
            for config_name, config_data in customizations.get("other_configs", {}).items():
                try:
                    config_path = config_data["path"]
                    
                    # Only restore if it's not homeserver.json (handled by backup)
                    if not config_name == "homeserver.json":
                        import json
                        with open(config_path, 'w') as f:
                            json.dump(config_data["content"], f, indent=4)
                        
                        log_message(f"✓ Restored user config: {config_name}")
                        configs_restored += 1
                    else:
                        log_message(f"Skipping {config_name} (handled by backup)")
                        
                except Exception as e:
                    log_message(f"✗ Exception restoring config {config_name}: {e}", "ERROR")
                    configs_failed += 1
            
            log_message(f"✓ User customizations restored: {themes_restored} themes, {configs_restored} configs")
            
            if themes_failed > 0 or configs_failed > 0:
                log_message(f"⚠ Some customizations failed: {themes_failed} themes, {configs_failed} configs", "WARNING")
            
            return themes_failed == 0 and configs_failed == 0
            
        except Exception as e:
            log_message(f"✗ User customization restoration failed: {e}", "ERROR")
            return False
    
    def _restore_directory_structure(self, target_path: str, structure: Dict[str, Any]) -> bool:
        """
        Restore a directory structure from captured data.
        
        Args:
            target_path: Path where directory should be restored
            structure: Directory structure data captured earlier
            
        Returns:
            bool: True if restoration successful, False otherwise
        """
        try:
            if structure.get("type") != "directory":
                log_message(f"Invalid structure type: {structure.get('type')}", "ERROR")
                return False
            
            # Create target directory
            os.makedirs(target_path, exist_ok=True)
            
            # Restore contents
            for item_name, item_data in structure.get("contents", {}).items():
                item_path = os.path.join(target_path, item_name)
                
                if item_data.get("type") == "file":
                    # Restore file
                    try:
                        with open(item_path, 'w', encoding='utf-8') as f:
                            f.write(item_data["content"])
                    except Exception as e:
                        log_message(f"Failed to restore file {item_path}: {e}", "ERROR")
                        return False
                        
                elif item_data.get("type") == "directory":
                    # Recursively restore subdirectory
                    if not self._restore_directory_structure(item_path, item_data):
                        return False
            
            return True
            
        except Exception as e:
            log_message(f"Error restoring directory {target_path}: {e}", "ERROR")
            return False
    
    def _stop_gunicorn_service(self) -> bool:
        """Stop gunicorn service to release file handles before file operations."""
        try:
            import subprocess
            
            log_message("Stopping gunicorn service...")
            
            # Use timeout to prevent hanging
            result = subprocess.run(
                ['timeout', '10', 'systemctl', 'stop', 'gunicorn.service'],
                capture_output=True,
                text=True,
                check=False  # Don't raise exception on failure
            )
            
            if result.returncode == 0:
                log_message("✓ Gunicorn service stopped successfully")
                return True
            else:
                log_message(f"⚠ Warning: Failed to stop gunicorn service: {result.stderr}", "WARNING")
                return False
                
        except Exception as e:
            log_message(f"⚠ Exception stopping gunicorn service: {e}", "WARNING")
            return False
    
    def _restore_permissions(self) -> bool:
        """Restore website permissions."""
        log_message("Restoring website permissions...")
        
        try:
            # Import PermissionManager
            from updates.utils.permissions import PermissionManager, PermissionTarget
            
            permission_manager = PermissionManager("website")
            
            # Define permission targets
            targets = [
                PermissionTarget(
                    path=self.base_dir,
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
            
            success = permission_manager.set_permissions(targets)
            
            if success:
                log_message("✓ Website permissions restored successfully")
            else:
                log_message("⚠ Some permission restoration failed", "WARNING")
            
            return success
            
        except Exception as e:
            log_message(f"⚠ Permission restoration failed: {e}", "WARNING")
            return False
    
    def _update_module_versions(self, new_content_version: str = None) -> bool:
        """Update module versions in index.json."""
        try:
            if new_content_version:
                # Update the content version in our module's index.json
                if "metadata" not in self.config:
                    self.config["metadata"] = {}
                
                self.config["metadata"]["content_version"] = new_content_version
                
                index_file = os.path.join(os.path.dirname(__file__), "..", "index.json")
                import json
                with open(index_file, 'w') as f:
                    json.dump(self.config, f, indent=4)
                
                log_message(f"Updated module content version to: {new_content_version}")
            
            return True
            
        except Exception as e:
            log_message(f"Failed to update module versions: {e}", "ERROR")
            return False
    
    def _update_homeserver_json_metadata(self, new_version: str) -> bool:
        """Update the version and timestamp in homeserver.json."""
        try:
            homeserver_config_path = os.path.join(self.base_dir, "src", "config", "homeserver.json")
            
            if not os.path.exists(homeserver_config_path):
                log_message(f"Homeserver config not found at {homeserver_config_path}", "WARNING")
                return False
            
            import json
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

    def _capture_and_backup_user_customizations(self) -> Optional[Dict[str, Any]]:
        """
        Capture user customizations in memory AND create filesystem backup.
        
        This method combines both the in-memory capture (for restoration) and
        filesystem backup (for safety net) into a single operation.
        
        Returns:
            Dict containing user customization state for restoration, or None if failed
        """
        try:
            log_message("Capturing and backing up user customizations...")
            
            # Create backup directory for filesystem backup
            backup_dir = "/var/backups/website/user_customizations"
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(backup_dir, f"user_customizations_{timestamp}")
            os.makedirs(backup_path, exist_ok=True)
            
            # Initialize in-memory capture structure
            customizations = {
                "timestamp": datetime.now().isoformat(),
                "backup_path": backup_path,  # Include backup path for reference
                "themes": {},
                "other_configs": {}
            }
            
            # Capture and backup custom themes (CRITICAL - never clobber these!)
            themes_dir = os.path.join(self.base_dir, 'src', 'config', 'themes')
            if os.path.exists(themes_dir):
                log_message("Capturing and backing up custom themes...")
                
                # Create filesystem backup of themes
                themes_backup_path = os.path.join(backup_path, 'themes')
                import shutil
                shutil.copytree(themes_dir, themes_backup_path, dirs_exist_ok=True)
                log_message(f"✓ Backed up themes to: {themes_backup_path}")
                
                # Capture themes in memory for restoration
                for theme_name in os.listdir(themes_dir):
                    theme_path = os.path.join(themes_dir, theme_name)
                    
                    if os.path.isdir(theme_path):
                        # Check if this is a user-created theme (not from repository)
                        theme_config_path = os.path.join(theme_path, 'theme.json')
                        
                        if os.path.exists(theme_config_path):
                            try:
                                import json
                                with open(theme_config_path, 'r') as f:
                                    theme_config = json.load(f)
                                
                                # Check if this is a user theme (has user_created flag or custom metadata)
                                is_user_theme = (
                                    theme_config.get("user_created", False) or
                                    theme_config.get("author") == "user" or
                                    theme_config.get("source") == "custom" or
                                    # If theme has custom modifications, treat as user theme
                                    theme_config.get("last_modified_by_user")
                                )
                                
                                if is_user_theme:
                                    log_message(f"✓ Capturing user theme: {theme_name}")
                                    
                                    # Capture entire theme directory for restoration
                                    customizations["themes"][theme_name] = {
                                        "path": theme_path,
                                        "config": theme_config,
                                        "files": self._capture_directory_structure(theme_path)
                                    }
                                else:
                                    log_message(f"Repository theme (will be updated): {theme_name}")
                                    
                            except Exception as e:
                                log_message(f"Warning: Could not read theme config for {theme_name}: {e}", "WARNING")
                                # If we can't read it, assume it's user-created and protect it
                                customizations["themes"][theme_name] = {
                                    "path": theme_path,
                                    "config": {"user_created": True, "protected": True},
                                    "files": self._capture_directory_structure(theme_path)
                                }
            
            # Capture and backup other user configuration files
            user_configs = [
                os.path.join(self.base_dir, 'src', 'config', 'homeserver.json'),  # Already backed up, but good to track
                os.path.join(self.base_dir, 'src', 'config', 'custom.css'),      # User custom CSS
                os.path.join(self.base_dir, 'src', 'config', 'user-settings.json')
            ]
            
            # Create filesystem backup of configs
            configs_backup_path = os.path.join(backup_path, 'configs')
            os.makedirs(configs_backup_path, exist_ok=True)
            
            for config_path in user_configs:
                if os.path.exists(config_path):
                    config_name = os.path.basename(config_path)
                    
                    # Create filesystem backup
                    config_backup_path = os.path.join(configs_backup_path, config_name)
                    shutil.copy2(config_path, config_backup_path)
                    log_message(f"✓ Backed up config: {config_name}")
                    
                    # Capture in memory for restoration
                    try:
                        import json
                        with open(config_path, 'r') as f:
                            config_data = json.load(f)
                        
                        customizations["other_configs"][config_name] = {
                            "path": config_path,
                            "content": config_data
                        }
                        
                        log_message(f"✓ Captured user config: {config_name}")
                        
                    except Exception as e:
                        log_message(f"Warning: Could not read config {config_path}: {e}", "WARNING")
            
            # Create backup manifest
            manifest = {
                "timestamp": datetime.now().isoformat(),
                "backup_path": backup_path,
                "themes_backed_up": themes_dir if os.path.exists(themes_dir) else None,
                "configs_backed_up": [c for c in user_configs if os.path.exists(c)],
                "description": "User customization backup for website update"
            }
            
            manifest_path = os.path.join(backup_path, 'backup_manifest.json')
            import json
            with open(manifest_path, 'w') as f:
                json.dump(manifest, f, indent=2)
            
            log_message(f"✓ User customizations captured and backed up: {len(customizations['themes'])} themes, {len(customizations['other_configs'])} configs")
            log_message(f"✓ Filesystem backup completed: {backup_path}")
            
            return customizations
            
        except Exception as e:
            log_message(f"✗ Failed to capture and backup user customizations: {e}", "ERROR")
            return None
