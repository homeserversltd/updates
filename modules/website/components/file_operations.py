"""
HOMESERVER Website Update Components
Copyright (C) 2024 HOMESERVER LLC

File Operations Component

Handles all file copying and synchronization operations for the website update system including:
- Safe non-destructive src directory updates
- Component-based file copying 
- Configuration preservation
- Detailed operation logging
"""

import os
import shutil
from typing import Dict, Any
from updates.index import log_message


class FileOperations:
    """Handles file operations for website updates."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.target_paths = config.get('config', {}).get('target_paths', {})
        
    def update_components(self, source_dir: str) -> bool:
        """
        Update all enabled components from the cloned repository.
        
        Args:
            source_dir: Path to the source repository directory
            
        Returns:
            bool: True if all components updated successfully, False otherwise
        """
        log_message(f"[FILE] Starting component update from source: {source_dir}")
        
        components = self.target_paths.get('components', {})
        log_message(f"[FILE] Found {len(components)} components to process")
        
        # Files that should be preserved during updates
        preserve_files = [
            "/var/www/homeserver/src/config/homeserver.json",
            "/var/www/homeserver/package-lock.json",
            "/var/www/homeserver/node_modules"
        ]
        log_message(f"[FILE] Preserving files: {preserve_files}")
        
        for component_name, component_config in components.items():
            log_message(f"[FILE] Processing component: {component_name}")
            
            if not component_config.get('enabled', False):
                log_message(f"[FILE] Component {component_name} is disabled, skipping")
                continue
            
            try:
                source_path = os.path.join(source_dir, component_config['source_path'])
                target_path = component_config['target_path']
                
                log_message(f"[FILE] Component {component_name}: {source_path} -> {target_path}")
                
                if not os.path.exists(source_path):
                    log_message(f"[FILE] ✗ Source path missing: {source_path}", "WARNING")
                    continue
                
                log_message(f"[FILE] ✓ Source path exists: {source_path}")
                
                # Special handling for src directory to preserve protected files
                if component_name == 'frontend' and target_path.endswith('/src'):
                    log_message(f"[FILE] Using selective update for frontend component: {component_name}")
                    self._selective_src_update(source_path, target_path)
                    log_message(f"[FILE] ✓ Frontend component updated via selective method")
                    continue
                
                # Standard component update for non-src components
                self._update_standard_component(component_name, source_path, target_path)
                
            except Exception as e:
                log_message(f"[FILE] ✗ Failed to update component {component_name}: {e}", "ERROR")
                return False
        
        log_message("[FILE] ✓ All enabled components updated successfully")
        return True
    
    def _update_standard_component(self, component_name: str, source_path: str, target_path: str) -> None:
        """
        Update a standard component (non-src) with simple replacement.
        
        Args:
            component_name: Name of the component
            source_path: Source file/directory path
            target_path: Target file/directory path
        """
        log_message(f"[FILE] Updating standard component: {component_name}")
        
        # Remove existing target if it exists
        if os.path.exists(target_path):
            if os.path.isdir(target_path):
                shutil.rmtree(target_path)
            else:
                os.remove(target_path)
        
        # Ensure parent directory exists
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        
        # Copy new content
        if os.path.isdir(source_path):
            shutil.copytree(source_path, target_path)
            kind = "dir"
        else:
            shutil.copy2(source_path, target_path)
            kind = "file"
        
        # Summarize instead of per-action details
        log_message(f"[FILE] ✓ Updated component: {component_name} ({kind})")
    
    def _selective_src_update(self, source_path: str, target_path: str) -> None:
        """
        Update src directory while preserving user configuration files using safe sync method.
        
        This method does NOT destructively remove the entire src directory first.
        Instead, it uses an rsync-like approach to safely update files.
        
        Args:
            source_path: Source src directory path
            target_path: Target src directory path (/var/www/homeserver/src)
        """
        config_backup = None
        config_path = os.path.join(target_path, 'config', 'homeserver.json')
        
        log_message(f"[FILE_COPY_DEBUG] Starting src update: {source_path} -> {target_path}")
        
        try:
            # STEP 1: Backup user configuration file
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config_backup = f.read()
                log_message("[FILE_COPY_DEBUG] ✓ Backed up homeserver.json")
            else:
                log_message("[FILE_COPY_DEBUG] No existing homeserver.json to backup")
            
            # STEP 2: Verify source exists
            if not os.path.exists(source_path):
                raise Exception(f"Source path does not exist: {source_path}")
            if not os.path.isdir(source_path):
                raise Exception(f"Source path is not a directory: {source_path}")
            
            log_message(f"[FILE_COPY_DEBUG] ✓ Source validated: {source_path}")
            
            # STEP 3: Use rsync-like behavior instead of destructive removal
            # Create target directory if it doesn't exist
            os.makedirs(target_path, exist_ok=True)
            log_message(f"[FILE_COPY_DEBUG] ✓ Target directory ensured: {target_path}")
            
            # Copy files from source to target, preserving what we can (quiet summary)
            log_message(f"[FILE] Syncing src directory (quiet)…")
            
            dirs_created = 0
            files_copied = 0
            for root, dirs, files in os.walk(source_path):
                # Calculate relative path from source
                rel_path = os.path.relpath(root, source_path)
                target_dir = target_path if rel_path == '.' else os.path.join(target_path, rel_path)

                # Create target directory if missing
                if not os.path.exists(target_dir):
                    os.makedirs(target_dir, exist_ok=True)
                    dirs_created += 1
                
                # Copy files
                for file in files:
                    src_file = os.path.join(root, file)
                    dst_file = os.path.join(target_dir, file)
                    
                    # Skip homeserver.json - we'll restore it later
                    if dst_file == config_path:
                        continue
                    
                    try:
                        shutil.copy2(src_file, dst_file)
                        files_copied += 1
                    except Exception as copy_error:
                        log_message(f"[FILE] ✗ Failed to copy {src_file}: {copy_error}", "ERROR")
                        raise
            
            log_message(f"[FILE] ✓ File sync completed ({dirs_created} dirs, {files_copied} files)")
            
            # STEP 4: Restore user configuration file
            config_dir = os.path.join(target_path, 'config')
            os.makedirs(config_dir, exist_ok=True)
            
            if config_backup:
                with open(config_path, 'w') as f:
                    f.write(config_backup)
                log_message("[FILE_COPY_DEBUG] ✓ Restored homeserver.json from backup")
            else:
                log_message("[FILE_COPY_DEBUG] No config backup to restore")
            
            log_message("[FILE_COPY_DEBUG] ✓ Selective src update completed successfully")
            
        except Exception as e:
            log_message(f"[FILE_COPY_DEBUG] ✗ Selective src update failed: {e}", "ERROR")
            log_message(f"[FILE_COPY_DEBUG] Source path: {source_path}", "ERROR")
            log_message(f"[FILE_COPY_DEBUG] Target path: {target_path}", "ERROR")
            log_message(f"[FILE_COPY_DEBUG] Config path: {config_path}", "ERROR")
            log_message(f"[FILE_COPY_DEBUG] Source exists: {os.path.exists(source_path) if source_path else 'None'}", "ERROR")
            log_message(f"[FILE_COPY_DEBUG] Target exists: {os.path.exists(target_path) if target_path else 'None'}", "ERROR")
            raise
    
    def validate_file_operations(self, source_dir: str) -> bool:
        """
        Validate that file operations can proceed successfully.
        
        Args:
            source_dir: Source directory to validate
            
        Returns:
            bool: True if validation passes, False otherwise
        """
        log_message("[FILE] Validating file operations...")
        
        components = self.target_paths.get('components', {})
        
        for component_name, component_config in components.items():
            if not component_config.get('enabled', False):
                continue
                
            source_path = os.path.join(source_dir, component_config['source_path'])
            target_path = component_config['target_path']
            
            # Check source exists
            if not os.path.exists(source_path):
                log_message(f"[FILE] ✗ Source missing for {component_name}: {source_path}", "ERROR")
                return False
            
            # Check target directory is writable
            target_parent = os.path.dirname(target_path)
            if not os.access(target_parent, os.W_OK):
                log_message(f"[FILE] ✗ Target directory not writable for {component_name}: {target_parent}", "ERROR")
                return False
            
            log_message(f"[FILE] ✓ Validation passed for {component_name}")
        
        log_message("[FILE] ✓ All file operations validated")
        return True
    
    def get_file_stats(self, source_dir: str) -> Dict[str, Any]:
        """
        Get statistics about the files that will be updated.
        
        Args:
            source_dir: Source directory to analyze
            
        Returns:
            Dict[str, Any]: File statistics
        """
        stats = {
            "components": {},
            "total_files": 0,
            "total_size": 0
        }
        
        components = self.target_paths.get('components', {})
        
        for component_name, component_config in components.items():
            if not component_config.get('enabled', False):
                continue
                
            source_path = os.path.join(source_dir, component_config['source_path'])
            
            if os.path.exists(source_path):
                if os.path.isdir(source_path):
                    file_count = sum(len(files) for _, _, files in os.walk(source_path))
                    dir_size = sum(
                        os.path.getsize(os.path.join(root, file))
                        for root, _, files in os.walk(source_path)
                        for file in files
                    )
                else:
                    file_count = 1
                    dir_size = os.path.getsize(source_path)
                
                stats["components"][component_name] = {
                    "files": file_count,
                    "size": dir_size
                }
                stats["total_files"] += file_count
                stats["total_size"] += dir_size
        
        log_message(f"[FILE] File stats: {stats['total_files']} files, {stats['total_size']} bytes")
        return stats
