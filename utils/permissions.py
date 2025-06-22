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
Permission Management Utilities

This module provides utilities for managing file and directory permissions
across all update modules. It handles common permission scenarios and
provides consistent error handling and logging.
"""

import os
import subprocess
import stat
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass
from .index import log_message


@dataclass
class PermissionTarget:
    """Represents a file or directory with its desired permissions."""
    path: str
    owner: str
    group: str
    mode: Union[str, int]  # Can be octal string like "755" or int like 0o755
    target_type: str = "auto"  # "file", "directory", or "auto"
    recursive: bool = False  # Apply permissions recursively for directories
    
    def __post_init__(self):
        """Convert mode to integer if it's a string."""
        if isinstance(self.mode, str):
            # Handle both "755" and "0o755" formats
            if self.mode.startswith('0o'):
                self.mode = int(self.mode, 8)
            else:
                self.mode = int(self.mode, 8)


class PermissionManager:
    """Manages file and directory permissions for update modules."""
    
    def __init__(self, module_name: str = "unknown"):
        self.module_name = module_name
    
    def set_permissions(self, targets: List[PermissionTarget]) -> bool:
        """
        Set permissions for multiple targets.
        
        Args:
            targets: List of PermissionTarget objects
            
        Returns:
            bool: True if all permissions were set successfully, False otherwise
        """
        if not targets:
            log_message("No permission targets specified", "WARNING")
            return True
        
        success_count = 0
        total_targets = len(targets)
        
        log_message(f"Setting permissions for {total_targets} targets...")
        
        for target in targets:
            if self._set_single_permission(target):
                success_count += 1
            else:
                log_message(f"Failed to set permissions for {target.path}", "ERROR")
        
        if success_count == total_targets:
            log_message(f"Successfully set permissions for all {total_targets} targets")
            return True
        else:
            log_message(f"Set permissions for {success_count}/{total_targets} targets", "WARNING")
            return success_count > 0  # Partial success is still useful
    
    def _set_single_permission(self, target: PermissionTarget) -> bool:
        """Set permissions for a single target."""
        path = target.path
        
        # Check if path exists
        if not os.path.exists(path):
            log_message(f"Skipping {path} - does not exist", "DEBUG")
            return True  # Not an error if path doesn't exist
        
        try:
            # Set ownership
            if not self._set_ownership(path, target.owner, target.group, target.recursive):
                return False
            
            # Set permissions
            if not self._set_mode(path, target.mode, target.recursive):
                return False
            
            log_message(f"✓ Set permissions for {path} ({target.owner}:{target.group} {oct(target.mode)})")
            return True
            
        except Exception as e:
            log_message(f"Error setting permissions for {path}: {e}", "ERROR")
            return False
    
    def _set_ownership(self, path: str, owner: str, group: str, recursive: bool = False) -> bool:
        """Set file/directory ownership."""
        try:
            cmd = ["chown"]
            if recursive and os.path.isdir(path):
                cmd.append("-R")
            cmd.extend([f"{owner}:{group}", path])
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            
            if result.returncode != 0:
                log_message(f"Failed to set ownership for {path}: {result.stderr}", "ERROR")
                return False
            
            return True
            
        except Exception as e:
            log_message(f"Error setting ownership for {path}: {e}", "ERROR")
            return False
    
    def _set_mode(self, path: str, mode: int, recursive: bool = False) -> bool:
        """Set file/directory permissions."""
        try:
            cmd = ["chmod"]
            if recursive and os.path.isdir(path):
                cmd.append("-R")
            cmd.extend([oct(mode)[2:], path])  # Convert 0o755 to "755"
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            
            if result.returncode != 0:
                log_message(f"Failed to set permissions for {path}: {result.stderr}", "ERROR")
                return False
            
            return True
            
        except Exception as e:
            log_message(f"Error setting permissions for {path}: {e}", "ERROR")
            return False
    
    def restore_service_permissions(self, service_name: str, 
                                  config_dirs: List[str] = None,
                                  data_dirs: List[str] = None,
                                  log_dirs: List[str] = None,
                                  binaries: List[str] = None,
                                  custom_targets: List[PermissionTarget] = None) -> bool:
        """
        Restore standard permissions for a service.
        
        This is a convenience method that handles common service permission patterns.
        
        Args:
            service_name: Name of the service (used for user/group)
            config_dirs: List of configuration directories
            data_dirs: List of data directories  
            log_dirs: List of log directories
            binaries: List of binary files
            custom_targets: List of custom permission targets
            
        Returns:
            bool: True if all permissions were restored successfully
        """
        targets = []
        
        # Configuration directories (service:service 755)
        for config_dir in (config_dirs or []):
            targets.append(PermissionTarget(
                path=config_dir,
                owner=service_name,
                group=service_name,
                mode=0o755,
                target_type="directory",
                recursive=True
            ))
        
        # Data directories (service:service 755)  
        for data_dir in (data_dirs or []):
            targets.append(PermissionTarget(
                path=data_dir,
                owner=service_name,
                group=service_name,
                mode=0o755,
                target_type="directory",
                recursive=True
            ))
        
        # Log directories (service:service 755)
        for log_dir in (log_dirs or []):
            targets.append(PermissionTarget(
                path=log_dir,
                owner=service_name,
                group=service_name,
                mode=0o755,
                target_type="directory",
                recursive=True
            ))
        
        # Binaries (root:root 755)
        for binary in (binaries or []):
            targets.append(PermissionTarget(
                path=binary,
                owner="root",
                group="root",
                mode=0o755,
                target_type="file"
            ))
        
        # Add custom targets
        if custom_targets:
            targets.extend(custom_targets)
        
        return self.set_permissions(targets)


# Convenience functions for common permission patterns
def create_service_permission_targets(service_name: str, 
                                    config_dir: str = None,
                                    data_dir: str = None,
                                    log_dir: str = None,
                                    binary_path: str = None,
                                    database_file: str = None) -> List[PermissionTarget]:
    """
    Create standard permission targets for a service.
    
    Args:
        service_name: Name of the service
        config_dir: Configuration directory path
        data_dir: Data directory path
        log_dir: Log directory path
        binary_path: Binary file path
        database_file: Database file path (will get 640 permissions)
        
    Returns:
        List[PermissionTarget]: List of permission targets
    """
    targets = []
    
    if binary_path:
        targets.append(PermissionTarget(
            path=binary_path,
            owner="root",
            group="root",
            mode=0o755,
            target_type="file"
        ))
    
    if config_dir:
        targets.append(PermissionTarget(
            path=config_dir,
            owner=service_name,
            group=service_name,
            mode=0o755,
            target_type="directory"
        ))
    
    if data_dir:
        targets.append(PermissionTarget(
            path=data_dir,
            owner=service_name,
            group=service_name,
            mode=0o755,
            target_type="directory"
        ))
    
    if log_dir:
        targets.append(PermissionTarget(
            path=log_dir,
            owner=service_name,
            group=service_name,
            mode=0o755,
            target_type="directory"
        ))
    
    if database_file:
        targets.append(PermissionTarget(
            path=database_file,
            owner=service_name,
            group=service_name,
            mode=0o640,
            target_type="file"
        ))
    
    return targets


def restore_service_permissions_simple(service_name: str,
                                     config_dir: str = None,
                                     data_dir: str = None,
                                     log_dir: str = None,
                                     binary_path: str = None,
                                     database_file: str = None) -> bool:
    """
    Simple function to restore standard service permissions.
    
    Returns:
        bool: True if all permissions were restored successfully
    """
    targets = create_service_permission_targets(
        service_name=service_name,
        config_dir=config_dir,
        data_dir=data_dir,
        log_dir=log_dir,
        binary_path=binary_path,
        database_file=database_file
    )
    
    if not targets:
        log_message("No permission targets specified", "WARNING")
        return True
    
    manager = PermissionManager(service_name)
    return manager.set_permissions(targets)


def fix_common_service_permissions(service_name: str) -> bool:
    """
    Fix permissions for common service locations.
    
    This function attempts to fix permissions for standard locations
    where services typically store their files.
    
    Args:
        service_name: Name of the service
        
    Returns:
        bool: True if permissions were fixed successfully
    """
    common_locations = [
        f"/etc/{service_name}",
        f"/var/lib/{service_name}",
        f"/var/log/{service_name}",
        f"/usr/local/bin/{service_name}",
        f"/opt/{service_name}"
    ]
    
    targets = []
    
    for location in common_locations:
        if os.path.exists(location):
            if location.startswith("/usr/local/bin/") or location.startswith("/opt/"):
                # Binaries should be root:root 755
                targets.append(PermissionTarget(
                    path=location,
                    owner="root",
                    group="root",
                    mode=0o755,
                    recursive=True if os.path.isdir(location) else False
                ))
            else:
                # Other directories should be service:service 755
                targets.append(PermissionTarget(
                    path=location,
                    owner=service_name,
                    group=service_name,
                    mode=0o755,
                    recursive=True
                ))
    
    if not targets:
        log_message(f"No common locations found for service {service_name}", "INFO")
        return True
    
    manager = PermissionManager(service_name)
    return manager.set_permissions(targets) 