"""
HOMESERVER Website Update Components
Copyright (C) 2024 HOMESERVER LLC

Tab Updater Component

Handles individual and batch premium tab updates including:
- Targeted backup of src/backend/build only
- Git clone clobber of specific tab directories
- Premium installer integration for reinstallation
- Build process and service restart
- Rollback capabilities

This component is designed for tab-specific updates where only tab directories
are clobbered, not the core website files.
"""

import os
import time
import shutil
import subprocess
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from updates.index import log_message

from .backup_manager import BackupManager
from .git_operations import GitOperations
from .build_manager import BuildManager
from .premium_tab_checker import PremiumTabChecker


class TabUpdater:
    """Handles individual and batch premium tab updates."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.base_dir = config.get('config', {}).get('target_paths', {}).get('base_directory', '/var/www/homeserver')
        self.premium_dir = os.path.join(self.base_dir, 'premium')
        
        # Initialize required components
        self.backup_manager = BackupManager(config)
        self.git = GitOperations(config)
        self.build = BuildManager(config)
        self.premium_tab_checker = PremiumTabChecker(config)
        
        # Premium installer path
        self.premium_installer_path = os.path.join(self.premium_dir, 'installer.py')
    
    def update_single_tab(self, tab_name: str) -> Dict[str, Any]:
        """
        Update a single premium tab.
        
        Args:
            tab_name: Name of the tab to update
            
        Returns:
            Dict containing update results
        """
        return self._update_tabs([tab_name])
    
    def update_batch_tabs(self, tab_names: List[str]) -> Dict[str, Any]:
        """
        Update multiple premium tabs in batch.
        
        Args:
            tab_names: List of tab names to update
            
        Returns:
            Dict containing update results
        """
        return self._update_tabs(tab_names)
    
    def _update_tabs(self, tab_names: List[str]) -> Dict[str, Any]:
        """
        Internal method to update tabs (single or batch).
        
        Args:
            tab_names: List of tab names to update
            
        Returns:
            Dict containing update results
        """
        start_time = time.time()
        
        log_message("="*60)
        log_message(f"STARTING TAB UPDATE{'S' if len(tab_names) > 1 else ''}: {', '.join(tab_names)}")
        log_message("="*60)
        
        result = {
            "success": False,
            "updated": False,
            "message": "",
            "tabs_updated": [],
            "tabs_failed": [],
            "error": None,
            "rollback_success": None,
            "duration": 0,
            "details": {}
        }
        
        try:
            # Step 1: Validate tab names and check if they exist
            log_message("Step 1: Validating tab names...")
            valid_tabs = self._validate_tab_names(tab_names)
            if not valid_tabs:
                raise Exception(f"No valid tabs found: {', '.join(tab_names)}")
            
            log_message(f"✓ Found {len(valid_tabs)} valid tabs to update")
            
            # Step 2: Create targeted backup (src/backend/build only)
            log_message("Step 2: Creating targeted backup...")
            if len(valid_tabs) == 1:
                backup_success = self.backup_manager.backup_for_tab_update(valid_tabs[0])
            else:
                backup_success = self.backup_manager.backup_for_batch_tab_updates(valid_tabs)
            
            if not backup_success:
                raise Exception("Failed to create targeted backup")
            
            # Step 3: Update each tab individually
            log_message("Step 3: Updating individual tabs...")
            for tab_name in valid_tabs:
                try:
                    log_message(f"Updating tab: {tab_name}")
                    tab_update_success = self._update_single_tab_files(tab_name)
                    
                    if tab_update_success:
                        result["tabs_updated"].append(tab_name)
                        log_message(f"✓ Successfully updated tab: {tab_name}")
                    else:
                        result["tabs_failed"].append(tab_name)
                        log_message(f"✗ Failed to update tab: {tab_name}")
                        
                except Exception as e:
                    log_message(f"✗ Exception updating tab {tab_name}: {e}", "ERROR")
                    result["tabs_failed"].append(tab_name)
            
            # Step 4: Reinstall updated tabs using premium installer
            log_message("Step 4: Reinstalling updated tabs...")
            if result["tabs_updated"]:
                reinstall_success = self._reinstall_tabs_via_premium_installer(result["tabs_updated"])
                if not reinstall_success:
                    log_message("⚠ Warning: Tab reinstallation failed", "WARNING")
            
            # Step 5: Run build process
            log_message("Step 5: Running build process...")
            if not self.build.run_build_process():
                raise Exception("Build process failed")
            
            # Step 6: Restart services
            log_message("Step 6: Restarting services...")
            if not self._restart_services():
                log_message("⚠ Warning: Service restart failed", "WARNING")
            
            # Success!
            result["success"] = len(result["tabs_updated"]) > 0
            result["updated"] = len(result["tabs_updated"]) > 0
            
            if result["tabs_failed"]:
                result["message"] = f"Partially successful: {len(result['tabs_updated'])} updated, {len(result['tabs_failed'])} failed"
            else:
                result["message"] = f"All {len(result['tabs_updated'])} tabs updated successfully"
            
            duration = time.time() - start_time
            result["duration"] = duration
            
            log_message("="*60)
            log_message(f"✓ TAB UPDATE{'S' if len(tab_names) > 1 else ''} COMPLETED ({duration:.1f}s)")
            log_message(f"✓ Updated: {len(result['tabs_updated'])} tabs")
            if result["tabs_failed"]:
                log_message(f"✗ Failed: {len(result['tabs_failed'])} tabs")
            log_message("="*60)
            
        except Exception as e:
            log_message(f"✗ Tab update failed: {e}", "ERROR")
            result["error"] = str(e)
            result["message"] = f"Update failed: {e}"
            
            # Attempt rollback
            log_message("Attempting rollback...")
            try:
                if len(valid_tabs) == 1:
                    rollback_success = self.backup_manager.restore_tab_backup(valid_tabs[0])
                else:
                    rollback_success = self.backup_manager.restore_batch_tab_backup()
                
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
            duration = time.time() - start_time
            result["duration"] = duration
        
        return result
    
    def _validate_tab_names(self, tab_names: List[str]) -> List[str]:
        """
        Validate that the specified tab names exist and are valid.
        
        Args:
            tab_names: List of tab names to validate
            
        Returns:
            List of valid tab names
        """
        valid_tabs = []
        
        for tab_name in tab_names:
            tab_path = os.path.join(self.premium_dir, tab_name)
            tab_index_path = os.path.join(tab_path, 'index.json')
            
            if not os.path.exists(tab_path):
                log_message(f"Tab directory not found: {tab_name}", "WARNING")
                continue
            
            if not os.path.exists(tab_index_path):
                log_message(f"Tab index.json not found: {tab_name}", "WARNING")
                continue
            
            # Check if tab is git-managed
            try:
                import json
                with open(tab_index_path, 'r') as f:
                    tab_config = json.load(f)
                
                config_section = tab_config.get("config", {})
                repository_info = config_section.get("repository", {})
                git_managed_flag = config_section.get("git_managed", False)
                
                has_repo_url = bool(repository_info.get("url"))
                has_repo_branch = bool(repository_info.get("branch"))
                
                if git_managed_flag and has_repo_url and has_repo_branch:
                    valid_tabs.append(tab_name)
                    log_message(f"✓ Valid git-managed tab: {tab_name}")
                else:
                    log_message(f"Tab {tab_name} is not git-managed, skipping", "WARNING")
                    
            except Exception as e:
                log_message(f"Error validating tab {tab_name}: {e}", "WARNING")
                continue
        
        return valid_tabs
    
    def _update_single_tab_files(self, tab_name: str) -> bool:
        """
        Update files for a single tab by cloning from its repository.
        
        Args:
            tab_name: Name of the tab to update
            
        Returns:
            bool: True if update successful, False otherwise
        """
        try:
            # Get tab configuration
            tab_index_path = os.path.join(self.premium_dir, tab_name, 'index.json')
            with open(tab_index_path, 'r') as f:
                import json
                tab_config = json.load(f)
            
            config_section = tab_config.get("config", {})
            repository_info = config_section.get("repository", {})
            repo_url = repository_info.get("url")
            repo_branch = repository_info.get("branch")
            
            if not repo_url or not repo_branch:
                log_message(f"Tab {tab_name} missing repository information", "ERROR")
                return False
            
            log_message(f"Cloning {tab_name} from {repo_url} (branch: {repo_branch})")
            
            # Create temporary directory for cloning
            import tempfile
            temp_dir = tempfile.mkdtemp(prefix=f"homeserver-tab-{tab_name}-")
            
            try:
                # Clone repository
                clone_cmd = [
                    'git', 'clone',
                    '--depth', '1',
                    '--branch', repo_branch,
                    repo_url,
                    temp_dir
                ]
                
                log_message(f"[TAB_UPDATER] Cloning {tab_name} from {repo_url} (branch: {repo_branch})")
                
                # Set environment to prevent credential prompts
                env = os.environ.copy()
                env['GIT_TERMINAL_PROMPT'] = '0'
                
                result = subprocess.run(
                    clone_cmd,
                    capture_output=True,
                    text=True,
                    stdin=subprocess.DEVNULL,
                    env=env,
                    timeout=120  # 2 minute timeout
                )
                
                if result.returncode != 0:
                    log_message(f"Clone failed for {tab_name}: {result.stderr}", "ERROR")
                    return False
                
                # Remove existing tab directory
                tab_path = os.path.join(self.premium_dir, tab_name)
                if os.path.exists(tab_path):
                    shutil.rmtree(tab_path)
                
                # Copy new content
                shutil.copytree(temp_dir, tab_path)
                
                log_message(f"✓ Successfully updated tab files: {tab_name}")
                return True
                
            finally:
                # Clean up temporary directory
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
                    
        except Exception as e:
            log_message(f"✗ Failed to update tab files for {tab_name}: {e}", "ERROR")
            return False
    
    def _reinstall_tabs_via_premium_installer(self, tab_names: List[str]) -> bool:
        """
        Reinstall tabs using the premium installer.
        
        Args:
            tab_names: List of tab names to reinstall
            
        Returns:
            bool: True if reinstallation successful, False otherwise
        """
        try:
            if not os.path.exists(self.premium_installer_path):
                log_message("Premium installer not found, cannot reinstall tabs", "WARNING")
                return False
            
            log_message(f"Reinstalling {len(tab_names)} tabs via premium installer...")
            
            # Use premium installer to reinstall tabs
            if len(tab_names) == 1:
                # Single tab - use reinstall command
                tab_name = tab_names[0]
                log_message(f"Reinstalling single tab: {tab_name}")
                success = self._run_premium_installer_reinstall(tab_name)
                if success:
                    log_message(f"✓ Successfully reinstalled tab: {tab_name}")
                else:
                    log_message(f"✗ Failed to reinstall tab: {tab_name}")
                    return False
            else:
                # Multiple tabs - use batch reinstall for efficiency
                log_message(f"Reinstalling {len(tab_names)} tabs using batch reinstall: {', '.join(tab_names)}")
                success = self._run_premium_installer_batch_reinstall(tab_names)
                if success:
                    log_message(f"✓ Successfully reinstalled {len(tab_names)} tabs")
                else:
                    log_message(f"✗ Failed to reinstall some tabs")
                    return False
            
            log_message("✓ Tab reinstallation completed")
            return True
            
        except Exception as e:
            log_message(f"✗ Tab reinstallation failed: {e}", "ERROR")
            return False
    
    def _run_premium_installer_reinstall(self, tab_name: str) -> bool:
        """
        Run premium installer reinstall command for a single tab.
        
        Args:
            tab_name: Name of the tab to reinstall
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            import subprocess
            
            # Run the premium installer reinstall command
            cmd = [
                "python3", 
                self.premium_installer_path, 
                "reinstall", 
                tab_name
            ]
            
            log_message(f"Running: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=os.path.dirname(self.premium_installer_path)
            )
            
            if result.returncode == 0:
                log_message(f"✓ Premium installer reinstall successful for {tab_name}")
                return True
            else:
                log_message(f"✗ Premium installer reinstall failed for {tab_name}")
                log_message(f"STDOUT: {result.stdout}")
                log_message(f"STDERR: {result.stderr}")
                return False
                
        except Exception as e:
            log_message(f"✗ Exception running premium installer reinstall for {tab_name}: {e}", "ERROR")
            return False
    
    def _run_premium_installer_batch_reinstall(self, tab_names: List[str]) -> bool:
        """
        Run premium installer batch reinstall command for multiple tabs.
        
        Args:
            tab_names: List of tab names to reinstall
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            import subprocess
            
            # Run the premium installer batch reinstall command
            cmd = [
                "python3", 
                self.premium_installer_path, 
                "reinstall"
            ] + tab_names
            
            log_message(f"Running: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=os.path.dirname(self.premium_installer_path)
            )
            
            if result.returncode == 0:
                log_message(f"✓ Premium installer batch reinstall successful for {len(tab_names)} tabs")
                return True
            else:
                log_message(f"✗ Premium installer batch reinstall failed")
                log_message(f"STDOUT: {result.stdout}")
                log_message(f"STDERR: {result.stderr}")
                return False
                
        except Exception as e:
            log_message(f"✗ Exception running premium installer batch reinstall: {e}", "ERROR")
            return False
    
    def _restart_services(self) -> bool:
        """Restart relevant services (excluding gunicorn - handled by orchestrator)."""
        log_message("Skipping service restart - gunicorn restart handled by orchestrator...")
        
        # No services to restart here - gunicorn restart is handled by the main orchestrator
        # to avoid killing the update process
        log_message("✓ Service restart phase completed (deferred to orchestrator)")
        return True
    
    def check_tab_updates(self) -> Dict[str, Any]:
        """
        Check for available tab updates.
        
        Returns:
            Dict containing update check results
        """
        log_message("Checking for premium tab updates...")
        
        try:
            # Use premium tab checker to get update status
            tab_updates = self.premium_tab_checker.check_all_premium_tabs()
            
            # Filter to only git-managed tabs
            git_managed_tabs = [tab for tab in tab_updates if tab["is_git_managed"]]
            tabs_needing_updates = [tab for tab in git_managed_tabs if tab["update_available"]]
            
            result = {
                "success": True,
                "total_tabs": len(tab_updates),
                "git_managed_tabs": len(git_managed_tabs),
                "tabs_needing_updates": len(tabs_needing_updates),
                "update_details": tabs_needing_updates,
                "summary": self.premium_tab_checker.get_update_summary(tab_updates)
            }
            
            log_message(f"Found {len(tabs_needing_updates)} tabs needing updates")
            return result
            
        except Exception as e:
            log_message(f"✗ Tab update check failed: {e}", "ERROR")
            return {
                "success": False,
                "error": str(e),
                "total_tabs": 0,
                "git_managed_tabs": 0,
                "tabs_needing_updates": 0,
                "update_details": [],
                "summary": "Check failed"
            }