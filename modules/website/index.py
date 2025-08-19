#!/usr/bin/env python3
"""
HOMESERVER Update Management System
Copyright (C) 2024 HOMESERVER LLC

HOMESERVER Website Update Module

Modular website update system that handles updating the HOMESERVER web interface 
from the GitHub repository with component-based architecture and existing utilities.

Key Features:
- Two-tier update methodology: Website updates vs. Tab updates
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
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime

# Import existing utilities
from updates.index import log_message
from updates.utils.state_manager import StateManager
from updates.utils.permissions import PermissionManager, PermissionTarget
from updates.utils.moduleUtils import conditional_config_return

# Import our new dedicated components
from .components import (
    WebsiteUpdater, 
    TabUpdater, 
    PremiumTabChecker
)


class WebsiteUpdateError(Exception):
    """Custom exception for website update failures."""
    pass


class WebsiteUpdateOrchestrator:
    """
    Main website update orchestrator that coordinates between website and tab updates.
    
    Uses dedicated components for:
    - Website updates: Comprehensive updates with premium tab restoration
    - Tab updates: Individual/batch tab updates with targeted backup
    - Update checking: Premium tab update detection
    """
    
    def __init__(self, module_path: str = None):
        if module_path is None:
            module_path = os.path.dirname(os.path.abspath(__file__))
        
        self.module_path = Path(module_path)
        self.index_file = self.module_path / "index.json"
        self.config = self._load_config()
        
        # Initialize dedicated update components
        self.website_updater = WebsiteUpdater(self.config)
        self.tab_updater = TabUpdater(self.config)
        self.premium_tab_checker = PremiumTabChecker(self.config)
        
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
    
    def check_updates(self) -> Dict[str, Any]:
        """
        Check for available updates (website and premium tabs).
        
        Returns:
            Dict containing comprehensive update check results
        """
        log_message("Checking for available updates...")
        
        result = {
            "success": False,
            "website_update_available": False,
            "tab_updates_available": False,
            "update_summary": "",
            "error": None,
            "details": {}
        }
        
        temp_dir = None
        
        try:
            # Check website updates
            log_message("Checking website for updates...")
            website_check = self._check_website_updates()
            result["website_update_available"] = website_check["update_needed"]
            result["details"]["website"] = website_check
            
            # Check premium tab updates
            log_message("Checking premium tabs for updates...")
            tab_check = self.tab_updater.check_tab_updates()
            result["details"]["premium_tabs"] = tab_check
            
            if tab_check["success"]:
                result["tab_updates_available"] = tab_check["tabs_needing_updates"] > 0
            else:
                log_message("⚠ Premium tab check failed", "WARNING")
            
            # Generate comprehensive update summary
            result["update_summary"] = self._generate_update_summary(
                website_check, 
                tab_check
            )
            
            result["success"] = True
            
            if result["website_update_available"] or result["tab_updates_available"]:
                log_message(f"Updates available: {result['update_summary']}")
            else:
                log_message("No updates available - everything is current")
            
        except Exception as e:
            log_message(f"✗ Update check failed: {e}", "ERROR")
            result["error"] = str(e)
        
        return result
    
    def _check_website_updates(self) -> Dict[str, Any]:
        """
        Check if website updates are needed.
        
        Returns:
            Dict containing website update check results
        """
        try:
            # Clone repository to check versions
            temp_dir = self.website_updater.git.clone_repository()
            if not temp_dir:
                return {
                    "update_needed": False,
                    "error": "Failed to clone repository for check"
                }
            
            # Check version updates
            update_needed, nuclear_restore, update_details = self.website_updater._check_version_update_needed(temp_dir)
            
            return {
                "update_needed": update_needed,
                "nuclear_restore": nuclear_restore,
                "update_details": update_details
            }
            
        except Exception as e:
            return {
                "update_needed": False,
                "error": str(e)
            }
        finally:
            if temp_dir:
                self.website_updater.git.cleanup_repository(temp_dir)
    
    def _generate_update_summary(self, website_check: Dict[str, Any], tab_check: Dict[str, Any]) -> str:
        """
        Generate human-readable update summary.
        
        Args:
            website_check: Website update check results
            tab_check: Premium tab update check results
            
        Returns:
            str: Human-readable update summary
        """
        summary_parts = []
        
        # Website update summary
        if website_check.get("update_needed"):
            reasons = website_check.get("update_details", {}).get("update_reasons", [])
            if reasons:
                summary_parts.append(f"Website: {', '.join(reasons)}")
            else:
                summary_parts.append("Website: Update needed")
        else:
            summary_parts.append("Website: Up to date")
        
        # Premium tab update summary
        if tab_check.get("success"):
            if tab_check.get("tabs_needing_updates", 0) > 0:
                summary_parts.append(f"Premium tabs: {tab_check['tabs_needing_updates']} update(s) available")
            else:
                summary_parts.append("Premium tabs: All up to date")
        else:
            summary_parts.append("Premium tabs: Check failed")
        
        return " | ".join(summary_parts)
    
    def update_website(self) -> Dict[str, Any]:
        """
        Perform comprehensive website update.
        
        Returns:
            Dict containing website update results
        """
        log_message("Starting comprehensive website update...")
        return self.website_updater.update()
    
    def update_single_tab(self, tab_name: str) -> Dict[str, Any]:
        """
        Update a single premium tab.
        
        Args:
            tab_name: Name of the tab to update
            
        Returns:
            Dict containing tab update results
        """
        log_message(f"Starting single tab update: {tab_name}")
        return self.tab_updater.update_single_tab(tab_name)
    
    def update_batch_tabs(self, tab_names: List[str]) -> Dict[str, Any]:
        """
        Update multiple premium tabs in batch.
        
        Args:
            tab_names: List of tab names to update
            
        Returns:
            Dict containing batch tab update results
        """
        log_message(f"Starting batch tab updates: {', '.join(tab_names)}")
        return self.tab_updater.update_batch_tabs(tab_names)
    
    def update_everything(self) -> Dict[str, Any]:
        """
        Update everything that needs updating (website + premium tabs).
        
        Returns:
            Dict containing comprehensive update results
        """
        log_message("Starting comprehensive update of everything...")
        
        result = {
            "success": False,
            "website_updated": False,
            "tabs_updated": False,
            "message": "",
            "error": None,
            "details": {}
        }
        
        try:
            # Step 1: Check what needs updating
            update_check = self.check_updates()
            if not update_check["success"]:
                raise Exception(f"Update check failed: {update_check.get('error')}")
            
            # Step 2: Update website if needed
            if update_check["website_update_available"]:
                log_message("Website update needed - updating...")
                website_result = self.update_website()
                result["website_updated"] = website_result["success"]
                result["details"]["website"] = website_result
                
                if not website_result["success"]:
                    log_message("⚠ Website update failed", "WARNING")
            else:
                log_message("Website is up to date")
                result["details"]["website"] = {"success": True, "message": "No update needed"}
            
            # Step 3: Update premium tabs if needed
            if update_check["tab_updates_available"]:
                log_message("Premium tab updates needed - updating...")
                
                # Get list of tabs needing updates
                tab_check = update_check["details"]["premium_tabs"]
                tabs_to_update = [tab["tab_name"] for tab in tab_check.get("update_details", [])]
                
                if tabs_to_update:
                    tab_result = self.update_batch_tabs(tabs_to_update)
                    result["tabs_updated"] = tab_result["success"]
                    result["details"]["tabs"] = tab_result
                    
                    if not tab_result["success"]:
                        log_message("⚠ Premium tab updates failed", "WARNING")
                else:
                    log_message("No premium tabs need updating")
                    result["details"]["tabs"] = {"success": True, "message": "No updates needed"}
            else:
                log_message("Premium tabs are up to date")
                result["details"]["tabs"] = {"success": True, "message": "No updates needed"}
            
            # Success!
            result["success"] = True
            result["message"] = "Comprehensive update completed"
            
            log_message("✓ Comprehensive update completed successfully")
            
        except Exception as e:
            log_message(f"✗ Comprehensive update failed: {e}", "ERROR")
            result["error"] = str(e)
            result["message"] = f"Update failed: {e}"
        
        return result


def main(args=None):
    """
    Main entry point for the website update module.
    
    Args:
        args: Optional command line arguments
    """
    log_message("Website update module started")
    
    # Module directory for reference
    module_dir = Path(__file__).parent
    
    # Lightweight check-only mode for orchestrator detection
    if args and isinstance(args, (list, tuple)) and ("--check" in args or "--check-only" in args):
        orchestrator = WebsiteUpdateOrchestrator()
        result = orchestrator.check_updates()
        
        # Include config only in debug mode
        result = conditional_config_return(result, orchestrator.config)
        
        return result
    
    try:
        orchestrator = WebsiteUpdateOrchestrator()
        
        # Check for updates first
        update_check = orchestrator.check_updates()
        
        if not update_check["success"]:
            result = {
                "success": False,
                "update_available": False,
                "error": update_check.get("error", "Update check failed")
            }
            
            # Include config only in debug mode
            result = conditional_config_return(result, orchestrator.config)
            
            return result
        
        # Determine what needs updating
        website_update_needed = update_check["website_update_available"]
        tab_updates_needed = update_check["tab_updates_available"]
        
        if not website_update_needed and not tab_updates_needed:
            result = {
                "success": True,
                "update_available": False,
                "message": "No updates available - everything is current"
            }
            
            # Include config only in debug mode
            result = conditional_config_return(result, orchestrator.config)
            
            return result
        
        # Perform appropriate update
        if website_update_needed:
            log_message("Website update needed - performing comprehensive update")
            result = orchestrator.update_website()
        elif tab_updates_needed:
            log_message("Premium tab updates needed - performing tab updates")
            
            # Get list of tabs needing updates
            tab_check = update_check["details"]["premium_tabs"]
            tabs_to_update = [tab["tab_name"] for tab in tab_check.get("update_details", [])]
            
            if tabs_to_update:
                result = orchestrator.update_batch_tabs(tabs_to_update)
            else:
                result = {"success": True, "message": "No tabs need updating"}
        else:
            # This shouldn't happen, but just in case
            result = {"success": True, "message": "No updates needed"}
        
        if result["success"]:
            log_message("Website update module completed successfully")
        else:
            log_message(f"Website update module failed: {result.get('message', 'Unknown error')}", "ERROR")
        
        # Include config only in debug mode
        result = conditional_config_return(result, orchestrator.config)
        
        return result
        
    except Exception as e:
        log_message(f"Website update module crashed: {e}", "ERROR")
        result = {
            "success": False,
            "updated": False,
            "message": f"Module crashed: {e}",
            "error": str(e),
            "rollback_success": None
        }
        
        # Include config only in debug mode for debugging crashes
        try:
            orchestrator = WebsiteUpdateOrchestrator()
            result = conditional_config_return(result, orchestrator.config)
        except:
            pass  # Don't fail if we can't get config
        
        return result


if __name__ == "__main__":
    import sys
    result = main(sys.argv[1:] if len(sys.argv) > 1 else None)
    sys.exit(0 if result["success"] else 1)
