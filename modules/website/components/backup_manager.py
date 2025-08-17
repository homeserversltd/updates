"""
HOMESERVER Website Update Components
Copyright (C) 2024 HOMESERVER LLC

Backup Manager Component

Handles backup strategies for different update scenarios:
- Website updates: Comprehensive backup of everything
- Tab updates: Targeted backup of src/backend/build only
- Batch operations: Coordinated backup strategies

Interfaces directly with the existing state manager for reliable backup/restore operations.
"""

import os
from typing import Dict, Any, List, Optional
from updates.index import log_message
from updates.utils.state_manager import StateManager


class BackupManager:
    """Manages backup strategies for website and tab update scenarios."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.base_dir = config.get('config', {}).get('target_paths', {}).get('base_directory', '/var/www/homeserver')
        
        # Initialize state manager with website backup directory
        self.state_manager = StateManager("/var/backups/website")
        
        # Define backup scopes for different scenarios
        self._define_backup_scopes()
    
    def _define_backup_scopes(self) -> None:
        """Define backup file lists for different update scenarios."""
        
        # Website update backup scope - comprehensive backup of everything
        self.website_backup_files = [
            os.path.join(self.base_dir, 'src'),           # React frontend source
            os.path.join(self.base_dir, 'backend'),       # Flask backend code
            os.path.join(self.base_dir, 'build'),         # Build assets (npm build output)
            os.path.join(self.base_dir, 'package.json'),  # NPM configuration
            os.path.join(self.base_dir, 'requirements.txt'), # Python dependencies
            os.path.join(self.base_dir, 'public'),        # Static assets
            os.path.join(self.base_dir, 'tsconfig.json'), # TypeScript configuration
            os.path.join(self.base_dir, 'premium'),       # Premium tab infrastructure + installed tabs
            os.path.join(self.base_dir, 'main.py'),       # Flask main file
            os.path.join(self.base_dir, 'config.py'),     # Flask config
        ]
        
        # Tab update backup scope - minimal backup for tab-specific updates
        self.tab_backup_files = [
            os.path.join(self.base_dir, 'src'),           # React frontend (needed for build)
            os.path.join(self.base_dir, 'backend'),       # Flask backend (needed for routes)
            os.path.join(self.base_dir, 'build'),         # Build assets (will be regenerated)
        ]
        
        # Services that need backup/restore
        self.website_services = ["gunicorn.service"]
        self.tab_services = ["gunicorn.service"]  # Same service, different context
    
    def backup_for_website_update(self, description: str = None) -> bool:
        """
        Create comprehensive backup for website update operations.
        
        This backup includes everything because git clone will clobber src/backend,
        and we'll need to reinstall all premium tabs after the update.
        
        Args:
            description: Optional description for the backup
            
        Returns:
            bool: True if backup successful, False otherwise
        """
        if description is None:
            description = "Pre-website-update comprehensive backup"
        
        log_message("[BACKUP] Creating comprehensive backup for website update...")
        log_message(f"[BACKUP] Scope: {len(self.website_backup_files)} files + {len(self.website_services)} services")
        
        try:
            # Filter to only existing files
            existing_files = [f for f in self.website_backup_files if os.path.exists(f)]
            
            if not existing_files:
                log_message("[BACKUP] ⚠ No files found to backup", "WARNING")
                return False
            
            log_message(f"[BACKUP] Backing up {len(existing_files)} existing files")
            
            backup_success = self.state_manager.backup_module_state(
                module_name="website",
                description=description,
                files=existing_files,
                services=self.website_services
            )
            
            if backup_success:
                log_message("[BACKUP] ✓ Website update backup created successfully")
            else:
                log_message("[BACKUP] ✗ Website update backup creation failed", "ERROR")
            
            return backup_success
            
        except Exception as e:
            log_message(f"[BACKUP] ✗ Website update backup failed: {e}", "ERROR")
            return False
    
    def backup_for_tab_update(self, tab_name: str, description: str = None) -> bool:
        """
        Create targeted backup for individual tab update operations.
        
        This backup only includes src/backend/build because:
        - Only the specific tab directory will be clobbered
        - We need src/backend for the build process
        - Build directory will be regenerated
        
        Args:
            tab_name: Name of the tab being updated
            description: Optional description for the backup
            
        Returns:
            bool: True if backup successful, False otherwise
        """
        if description is None:
            description = f"Pre-tab-update backup for {tab_name}"
        
        log_message(f"[BACKUP] Creating targeted backup for tab update: {tab_name}")
        log_message(f"[BACKUP] Scope: {len(self.tab_backup_files)} files + {len(self.tab_services)} services")
        
        try:
            # Filter to only existing files
            existing_files = [f for f in self.tab_backup_files if os.path.exists(f)]
            
            if not existing_files:
                log_message("[BACKUP] ⚠ No files found to backup", "WARNING")
                return False
            
            log_message(f"[BACKUP] Backing up {len(existing_files)} existing files")
            
            backup_success = self.state_manager.backup_module_state(
                module_name=f"website_tab_{tab_name}",
                description=description,
                files=existing_files,
                services=self.tab_services
            )
            
            if backup_success:
                log_message(f"[BACKUP] ✓ Tab update backup created successfully for {tab_name}")
            else:
                log_message(f"[BACKUP] ✗ Tab update backup creation failed for {tab_name}", "ERROR")
            
            return backup_success
            
        except Exception as e:
            log_message(f"[BACKUP] ✗ Tab update backup failed for {tab_name}: {e}", "ERROR")
            return False
    
    def backup_for_batch_tab_updates(self, tab_names: List[str], description: str = None) -> bool:
        """
        Create targeted backup for batch tab update operations.
        
        This is the same scope as individual tab updates since we're still
        only updating tab directories, not the core website.
        
        Args:
            tab_names: List of tab names being updated
            description: Optional description for the backup
            
        Returns:
            bool: True if backup successful, False otherwise
        """
        if description is None:
            tab_list = ", ".join(tab_names)
            description = f"Pre-batch-tab-update backup for: {tab_list}"
        
        log_message(f"[BACKUP] Creating targeted backup for batch tab updates: {', '.join(tab_names)}")
        log_message(f"[BACKUP] Scope: {len(self.tab_backup_files)} files + {len(self.tab_services)} services")
        
        try:
            # Filter to only existing files
            existing_files = [f for f in self.tab_backup_files if os.path.exists(f)]
            
            if not existing_files:
                log_message("[BACKUP] ⚠ No files found to backup", "WARNING")
                return False
            
            log_message(f"[BACKUP] Backing up {len(existing_files)} existing files")
            
            backup_success = self.state_manager.backup_module_state(
                module_name="website_batch_tabs",
                description=description,
                files=existing_files,
                services=self.tab_services
            )
            
            if backup_success:
                log_message(f"[BACKUP] ✓ Batch tab update backup created successfully")
            else:
                log_message(f"[BACKUP] ✗ Batch tab update backup creation failed", "ERROR")
            
            return backup_success
            
        except Exception as e:
            log_message(f"[BACKUP] ✗ Batch tab update backup failed: {e}", "ERROR")
            return False
    
    def restore_website_backup(self) -> bool:
        """
        Restore website backup (comprehensive backup).
        
        Returns:
            bool: True if restore successful, False otherwise
        """
        log_message("[BACKUP] Restoring website backup...")
        
        try:
            restore_success = self.state_manager.restore_module_state("website")
            
            if restore_success:
                log_message("[BACKUP] ✓ Website backup restored successfully")
            else:
                log_message("[BACKUP] ✗ Website backup restore failed", "ERROR")
            
            return restore_success
            
        except Exception as e:
            log_message(f"[BACKUP] ✗ Website backup restore failed: {e}", "ERROR")
            return False
    
    def restore_tab_backup(self, tab_name: str) -> bool:
        """
        Restore tab-specific backup.
        
        Args:
            tab_name: Name of the tab to restore
            
        Returns:
            bool: True if restore successful, False otherwise
        """
        log_message(f"[BACKUP] Restoring tab backup for {tab_name}...")
        
        try:
            restore_success = self.state_manager.restore_module_state(f"website_tab_{tab_name}")
            
            if restore_success:
                log_message(f"[BACKUP] ✓ Tab backup restored successfully for {tab_name}")
            else:
                log_message(f"[BACKUP] ✗ Tab backup restore failed for {tab_name}", "ERROR")
            
            return restore_success
            
        except Exception as e:
            log_message(f"[BACKUP] ✗ Tab backup restore failed for {tab_name}: {e}", "ERROR")
            return False
    
    def restore_batch_tab_backup(self) -> bool:
        """
        Restore batch tab backup.
        
        Returns:
            bool: True if restore successful, False otherwise
        """
        log_message("[BACKUP] Restoring batch tab backup...")
        
        try:
            restore_success = self.state_manager.restore_module_state("website_batch_tabs")
            
            if restore_success:
                log_message("[BACKUP] ✓ Batch tab backup restored successfully")
            else:
                log_message("[BACKUP] ✗ Batch tab backup restore failed", "ERROR")
            
            return restore_success
            
        except Exception as e:
            log_message(f"[BACKUP] ✗ Batch tab backup restore failed: {e}", "ERROR")
            return False
    
    def get_backup_status(self) -> Dict[str, Any]:
        """
        Get status of all available backups.
        
        Returns:
            Dict containing backup status information
        """
        log_message("[BACKUP] Checking backup status...")
        
        backup_status = {
            "website_backup_exists": False,
            "tab_backups": {},
            "batch_tab_backup_exists": False,
            "total_backups": 0
        }
        
        try:
            # Check website backup
            backup_status["website_backup_exists"] = self.state_manager.has_backup("website")
            
            # Check batch tab backup
            backup_status["batch_tab_backup_exists"] = self.state_manager.has_backup("website_batch_tabs")
            
            # Check individual tab backups (we'd need to know tab names to check these)
            # For now, just note that we can't easily enumerate them
            
            # Get total backup count
            all_backups = self.state_manager.list_module_backups()
            backup_status["total_backups"] = len(all_backups)
            
            log_message(f"[BACKUP] Backup status: {backup_status['total_backups']} total backups")
            log_message(f"[BACKUP] Website backup: {'✓' if backup_status['website_backup_exists'] else '✗'}")
            log_message(f"[BACKUP] Batch tab backup: {'✓' if backup_status['batch_tab_backup_exists'] else '✗'}")
            
        except Exception as e:
            log_message(f"[BACKUP] ✗ Failed to get backup status: {e}", "ERROR")
        
        return backup_status
    
    def cleanup_old_backups(self, keep_website: bool = True) -> bool:
        """
        Clean up old backups, keeping website backup if specified.
        
        Args:
            keep_website: Whether to keep the website backup
            
        Returns:
            bool: True if cleanup successful, False otherwise
        """
        log_message("[BACKUP] Cleaning up old backups...")
        
        try:
            all_backups = self.state_manager.list_module_backups()
            cleaned_count = 0
            
            for module_name in all_backups:
                # Skip website backup if requested
                if keep_website and module_name == "website":
                    log_message("[BACKUP] Keeping website backup")
                    continue
                
                # Remove other backups
                if self.state_manager.remove_module_backup(module_name):
                    log_message(f"[BACKUP] ✓ Removed backup: {module_name}")
                    cleaned_count += 1
                else:
                    log_message(f"[BACKUP] ⚠ Failed to remove backup: {module_name}", "WARNING")
            
            log_message(f"[BACKUP] ✓ Cleanup completed: {cleaned_count} backups removed")
            return True
            
        except Exception as e:
            log_message(f"[BACKUP] ✗ Backup cleanup failed: {e}", "ERROR")
            return False
