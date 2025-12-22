"""
HOMESERVER Website Update Components
Copyright (C) 2024 HOMESERVER LLC

Premium Tab Update Checker Component

Handles checking individual premium tabs for updates by:
- Walking through /premium/{tabName}/index.json files
- Determining git-managed status from configuration
- Comparing local vs repository versions
- Returning update availability status for each tab
"""

import os
import json
import subprocess
import tempfile
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from updates.index import log_message


class PremiumTabChecker:
    """Checks individual premium tabs for available updates."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.base_dir = config.get('config', {}).get('target_paths', {}).get('base_directory', '/var/www/homeserver')
        self.premium_dir = os.path.join(self.base_dir, 'premium')
        
    def check_all_premium_tabs(self) -> List[Dict[str, Any]]:
        """
        Check all premium tabs for available updates.
        
        Returns:
            List[Dict]: List of tab update status information
        """
        log_message("[PREMIUM_CHECK] Checking premium tabs for updates...")
        
        if not os.path.exists(self.premium_dir):
            log_message("[PREMIUM_CHECK] Premium directory not found", "WARNING")
            return []
        
        tab_statuses = []
        
        try:
            # Walk through premium directory looking for tab folders
            for item in os.listdir(self.premium_dir):
                item_path = os.path.join(self.premium_dir, item)
                
                # Skip non-directories and special files
                if not os.path.isdir(item_path) or item.startswith('.'):
                    continue
                
                # Check if this is a premium tab by looking for index.json
                tab_index_path = os.path.join(item_path, 'index.json')
                if not os.path.exists(tab_index_path):
                    continue
                
                log_message(f"[PREMIUM_CHECK] Checking tab: {item}")
                tab_status = self._check_single_tab(item, item_path, tab_index_path)
                tab_statuses.append(tab_status)
                
        except Exception as e:
            log_message(f"[PREMIUM_CHECK] ✗ Error checking premium tabs: {e}", "ERROR")
            return []
        
        log_message(f"[PREMIUM_CHECK] ✓ Checked {len(tab_statuses)} premium tabs")
        return tab_statuses
    
    def _check_single_tab(self, tab_name: str, tab_path: str, index_path: str) -> Dict[str, Any]:
        """
        Check a single premium tab for updates.
        
        Args:
            tab_name: Name of the tab
            tab_path: Full path to the tab directory
            index_path: Path to the tab's index.json file
            
        Returns:
            Dict containing tab update status information
        """
        tab_status = {
            "tab_name": tab_name,
            "tab_path": tab_path,
            "is_git_managed": False,
            "has_update_repo": False,
            "current_version": None,
            "latest_version": None,
            "update_available": False,
            "update_type": "not_git_managed",
            "repo_url": None,
            "repo_branch": None,
            "error": None
        }
        
        try:
            # Load tab configuration
            with open(index_path, 'r') as f:
                tab_config = json.load(f)
            
            # Extract version information
            tab_status["current_version"] = tab_config.get("version", "unknown")
            
            # Check if tab is git-managed
            config_section = tab_config.get("config", {})
            repository_info = config_section.get("repository", {})
            git_managed_flag = config_section.get("git_managed", False)
            
            # Tab is git-managed if it has repository info AND git_managed flag is true
            has_repo_url = bool(repository_info.get("url"))
            has_repo_branch = bool(repository_info.get("branch"))
            
            tab_status["is_git_managed"] = git_managed_flag and has_repo_url and has_repo_branch
            tab_status["has_update_repo"] = has_repo_url and has_repo_branch
            tab_status["repo_url"] = repository_info.get("url")
            tab_status["repo_branch"] = repository_info.get("branch")
            
            if not tab_status["is_git_managed"]:
                tab_status["update_type"] = "not_git_managed"
                log_message(f"[PREMIUM_CHECK] Tab {tab_name} is not git-managed")
                return tab_status
            
            # Tab is git-managed, check for updates
            log_message(f"[PREMIUM_CHECK] Tab {tab_name} is git-managed, checking for updates...")
            tab_status["update_type"] = "individual_tab"
            
            # Check repository for newer version
            latest_version = self._get_repository_version(
                tab_status["repo_url"], 
                tab_status["repo_branch"]
            )
            
            if latest_version:
                tab_status["latest_version"] = latest_version
                
                # Compare versions
                if self._compare_versions(latest_version, tab_status["current_version"]) > 0:
                    tab_status["update_available"] = True
                    log_message(f"[PREMIUM_CHECK] ✓ Tab {tab_name} has update: {tab_status['current_version']} → {latest_version}")
                else:
                    log_message(f"[PREMIUM_CHECK] Tab {tab_name} is up to date: {tab_status['current_version']}")
            else:
                log_message(f"[PREMIUM_CHECK] ⚠ Could not determine latest version for {tab_name}")
                tab_status["error"] = "Failed to retrieve repository version"
                
        except Exception as e:
            log_message(f"[PREMIUM_CHECK] ✗ Error checking tab {tab_name}: {e}", "ERROR")
            tab_status["error"] = str(e)
        
        return tab_status
    
    def _get_repository_version(self, repo_url: str, branch: str) -> Optional[str]:
        """
        Get the latest version from a git repository.
        
        Args:
            repo_url: Git repository URL
            branch: Git branch name
            
        Returns:
            Optional[str]: Latest version string, or None if failed
        """
        temp_dir = None
        
        try:
            # Create temporary directory for cloning
            temp_dir = tempfile.mkdtemp(prefix="homeserver-tab-check-")
            
            log_message(f"[PREMIUM_CHECK] Cloning {repo_url} (branch: {branch}) to check version...")
            
            # Clone repository (shallow clone for efficiency)
            clone_cmd = [
                'git', 'clone',
                '--depth', '1',
                '--branch', branch,
                repo_url,
                temp_dir
            ]
            
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
                log_message(f"[PREMIUM_CHECK] Clone failed: {result.stderr}", "WARNING")
                return None
            
            # Look for index.json in the cloned repository
            repo_index_path = os.path.join(temp_dir, 'index.json')
            if not os.path.exists(repo_index_path):
                log_message(f"[PREMIUM_CHECK] No index.json found in repository", "WARNING")
                return None
            
            # Read version from repository index.json
            with open(repo_index_path, 'r') as f:
                repo_config = json.load(f)
            
            latest_version = repo_config.get("version")
            if latest_version:
                log_message(f"[PREMIUM_CHECK] Found repository version: {latest_version}")
                return latest_version
            else:
                log_message(f"[PREMIUM_CHECK] No version found in repository index.json", "WARNING")
                return None
                
        except subprocess.TimeoutExpired:
            log_message(f"[PREMIUM_CHECK] Repository clone timed out", "WARNING")
            return None
        except Exception as e:
            log_message(f"[PREMIUM_CHECK] Error checking repository: {e}", "WARNING")
            return None
        finally:
            # Clean up temporary directory
            if temp_dir and os.path.exists(temp_dir):
                try:
                    import shutil
                    shutil.rmtree(temp_dir)
                except Exception:
                    pass
    
    def _compare_versions(self, version1: str, version2: str) -> int:
        """
        Compare two version strings.
        
        Args:
            version1: First version string
            version2: Second version string
            
        Returns:
            int: -1 if version1 < version2, 0 if equal, 1 if version1 > version2
        """
        try:
            # Split versions into components and convert to integers
            v1_parts = [int(x) for x in version1.split('.')]
            v2_parts = [int(x) for x in version2.split('.')]
            
            # Pad shorter version with zeros
            max_length = max(len(v1_parts), len(v2_parts))
            v1_parts.extend([0] * (max_length - len(v1_parts)))
            v2_parts.extend([0] * (max_length - len(v2_parts)))
            
            # Compare each component
            for v1, v2 in zip(v1_parts, v2_parts):
                if v1 < v2:
                    return -1
                elif v1 > v2:
                    return 1
            
            return 0  # Versions are equal
            
        except Exception as e:
            log_message(f"[PREMIUM_CHECK] Error comparing versions '{version1}' and '{version2}': {e}", "WARNING")
            # If we can't compare, assume no update available
            return 0
    
    def get_update_summary(self, tab_statuses: List[Dict[str, Any]]) -> str:
        """
        Generate a human-readable summary of premium tab updates.
        
        Args:
            tab_statuses: List of tab status dictionaries
            
        Returns:
            str: Human-readable update summary
        """
        if not tab_statuses:
            return "No premium tabs found"
        
        # Count different types of tabs
        git_managed_count = sum(1 for tab in tab_statuses if tab["is_git_managed"])
        update_available_count = sum(1 for tab in tab_statuses if tab["update_available"])
        
        summary_parts = []
        
        if git_managed_count > 0:
            if update_available_count > 0:
                summary_parts.append(f"Premium tabs: {update_available_count} update(s) available")
                
                # List tabs with updates
                for tab in tab_statuses:
                    if tab["update_available"]:
                        summary_parts.append(f"  - {tab['tab_name']}: {tab['current_version']} → {tab['latest_version']}")
            else:
                summary_parts.append("Premium tabs: All up to date")
        else:
            summary_parts.append("Premium tabs: None are git-managed")
        
        return " | ".join(summary_parts)
