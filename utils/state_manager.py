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
State Manager for Updates System

Simple single-backup-per-module state management system. Each module gets exactly one 
backup slot that is clobbered on each update cycle. No timelines, no cleanup needed.

Key Features:
- Single backup per module (no timeline management)
- Automatic previous backup clobbering
- File, service, and database state capture
- Simple restore by module name
- Predictable backup locations

Usage:
    from updates.utils import StateManager
    
    state_manager = StateManager("/var/backups/updates")
    
    # Create backup (clobbers any existing backup for this module)
    state_manager.backup_module_state("atuin", files=["/path/to/config"], services=["service"])
    
    # Restore if needed
    state_manager.restore_module_state("atuin")
"""

import os
import json
import shutil
import subprocess
import time
import hashlib
import tempfile
import stat
import pwd
import grp
from pathlib import Path
from typing import Dict, List, Any, Optional, Union, Tuple
from dataclasses import dataclass, asdict
from .index import log_message

class StateManagerError(Exception):
    """Custom exception for state manager operation failures."""
    pass

@dataclass
class FilePermissionInfo:
    """Information about file permissions and ownership."""
    path: str
    mode: int
    uid: int
    gid: int
    owner: str
    group: str
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FilePermissionInfo':
        return cls(**data)

@dataclass
class ModuleBackupInfo:
    """Information about a module's backup state."""
    module_name: str
    timestamp: int
    description: str
    backup_dir: str
    files: List[str]
    services: List[str]  
    databases: List[Dict[str, str]]
    checksum: str
    file_permissions: List[Dict[str, Any]]  # Store permission info
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ModuleBackupInfo':
        # Handle backward compatibility for existing backups without file_permissions
        if 'file_permissions' not in data:
            data['file_permissions'] = []
        return cls(**data)

class StateManager:
    """
    Simple single-backup-per-module state management system.
    
    Each module gets exactly one backup slot. Creating a new backup
    clobbers the previous backup for that module.
    """
    
    def __init__(self, backup_dir: str = "/var/backups/updates"):
        self.backup_root = Path(backup_dir)
        self.backup_root.mkdir(parents=True, exist_ok=True)
        self.index_file = self.backup_root / "module_backups.json"
        
    def _get_module_backup_dir(self, module_name: str) -> Path:
        """Get the backup directory for a specific module."""
        return self.backup_root / f"{module_name}_backup"
    
    def _get_file_permissions(self, file_path: str) -> Optional[FilePermissionInfo]:
        """Get file permissions and ownership information."""
        try:
            if not os.path.exists(file_path):
                return None
            
            stat_info = os.stat(file_path)
            
            # Get owner and group names
            try:
                owner = pwd.getpwuid(stat_info.st_uid).pw_name
            except KeyError:
                owner = str(stat_info.st_uid)
            
            try:
                group = grp.getgrgid(stat_info.st_gid).gr_name
            except KeyError:
                group = str(stat_info.st_gid)
            
            return FilePermissionInfo(
                path=file_path,
                mode=stat_info.st_mode,
                uid=stat_info.st_uid,
                gid=stat_info.st_gid,
                owner=owner,
                group=group
            )
        except Exception as e:
            log_message(f"Failed to get permissions for {file_path}: {e}", "WARNING")
            return None
    
    def _capture_permissions(self, files: List[str]) -> List[Dict[str, Any]]:
        """Capture permissions for all files and directories."""
        permissions = []
        
        for file_path in files:
            if not os.path.exists(file_path):
                continue
            
            # Get permissions for the main path
            perm_info = self._get_file_permissions(file_path)
            if perm_info:
                permissions.append(perm_info.to_dict())
            
            # If it's a directory, capture permissions for all contents recursively
            if os.path.isdir(file_path):
                for root, dirs, files_in_dir in os.walk(file_path):
                    # Capture directory permissions
                    if root != file_path:  # Don't duplicate the main directory
                        perm_info = self._get_file_permissions(root)
                        if perm_info:
                            permissions.append(perm_info.to_dict())
                    
                    # Capture file permissions
                    for file_name in files_in_dir:
                        full_path = os.path.join(root, file_name)
                        perm_info = self._get_file_permissions(full_path)
                        if perm_info:
                            permissions.append(perm_info.to_dict())
        
        log_message(f"Captured permissions for {len(permissions)} files/directories")
        return permissions
    
    def _restore_permissions(self, permissions: List[Dict[str, Any]]) -> bool:
        """Restore file permissions and ownership."""
        if not permissions:
            return True
        
        success_count = 0
        
        for perm_data in permissions:
            try:
                perm_info = FilePermissionInfo.from_dict(perm_data)
                
                if not os.path.exists(perm_info.path):
                    log_message(f"Cannot restore permissions for non-existent path: {perm_info.path}", "WARNING")
                    continue
                
                # Restore ownership
                try:
                    os.chown(perm_info.path, perm_info.uid, perm_info.gid)
                except OSError as e:
                    log_message(f"Failed to restore ownership for {perm_info.path}: {e}", "WARNING")
                
                # Restore permissions
                try:
                    os.chmod(perm_info.path, stat.S_IMODE(perm_info.mode))
                except OSError as e:
                    log_message(f"Failed to restore permissions for {perm_info.path}: {e}", "WARNING")
                
                success_count += 1
                
            except Exception as e:
                log_message(f"Failed to restore permissions for entry: {e}", "WARNING")
        
        log_message(f"Restored permissions for {success_count}/{len(permissions)} files/directories")
        return success_count > 0
    
    def _calculate_checksum(self, file_path: str) -> str:
        """Calculate SHA-256 checksum of a file or directory."""
        if not os.path.exists(file_path):
            return ""
        
        sha256_hash = hashlib.sha256()
        
        if os.path.isdir(file_path):
            # For directories, hash all files recursively
            for root, dirs, files in os.walk(file_path):
                # Sort for consistent ordering
                dirs.sort()
                files.sort()
                
                for file in files:
                    file_path_full = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path_full, file_path)
                    sha256_hash.update(rel_path.encode())
                    
                    try:
                        with open(file_path_full, 'rb') as f:
                            for chunk in iter(lambda: f.read(4096), b""):
                                sha256_hash.update(chunk)
                    except (IOError, OSError):
                        # Skip files we can't read
                        continue
        else:
            # For files, hash the content
            try:
                with open(file_path, "rb") as f:
                    for chunk in iter(lambda: f.read(4096), b""):
                        sha256_hash.update(chunk)
            except (IOError, OSError):
                return ""
        
        return sha256_hash.hexdigest()
    
    def _load_module_index(self) -> Dict[str, ModuleBackupInfo]:
        """Load the module backup index."""
        if not self.index_file.exists():
            return {}
        
        try:
            with open(self.index_file, 'r') as f:
                data = json.load(f)
                return {
                    module_name: ModuleBackupInfo.from_dict(backup_data)
                    for module_name, backup_data in data.items()
                }
        except Exception as e:
            log_message(f"Failed to load module backup index: {e}", "WARNING")
            return {}
    
    def _save_module_index(self, module_backups: Dict[str, ModuleBackupInfo]) -> None:
        """Save the module backup index."""
        try:
            data = {
                module_name: backup.to_dict() 
                for module_name, backup in module_backups.items()
            }
            with open(self.index_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            log_message(f"Failed to save module backup index: {e}", "ERROR")
    
    def _backup_files(self, module_backup_dir: Path, files: List[str]) -> bool:
        """Backup specified files to the module backup directory."""
        files_dir = module_backup_dir / "files"
        files_dir.mkdir(parents=True, exist_ok=True)
        
        success_count = 0
        
        for file_path in files:
            source = Path(file_path)
            if not source.exists():
                log_message(f"Source file not found, skipping: {file_path}", "WARNING")
                continue
            
            try:
                # Create relative path structure in backup
                if source.is_absolute():
                    # Convert absolute path to relative backup path
                    rel_path = str(source).lstrip('/')
                else:
                    rel_path = str(source)
                
                backup_target = files_dir / rel_path
                backup_target.parent.mkdir(parents=True, exist_ok=True)
                
                if source.is_dir():
                    if backup_target.exists():
                        shutil.rmtree(backup_target)
                    shutil.copytree(source, backup_target)
                else:
                    shutil.copy2(source, backup_target)
                
                success_count += 1
                log_message(f"Backed up: {file_path}")
                
            except Exception as e:
                log_message(f"Failed to backup {file_path}: {e}", "WARNING")
        
        return success_count > 0
    
    def _backup_services(self, module_backup_dir: Path, services: List[str]) -> bool:
        """Backup service states to the module backup directory."""
        if not services:
            return True
        
        services_file = module_backup_dir / "services.json"
        
        try:
            service_states = {}
            
            for service in services:
                # Get service status
                result = subprocess.run(
                    ["systemctl", "is-active", service],
                    capture_output=True, text=True
                )
                is_active = result.stdout.strip() == "active"
                
                # Get service enabled status
                result = subprocess.run(
                    ["systemctl", "is-enabled", service],
                    capture_output=True, text=True
                )
                is_enabled = result.stdout.strip() == "enabled"
                
                service_states[service] = {
                    "active": is_active,
                    "enabled": is_enabled
                }
            
            # Save service states
            with open(services_file, 'w') as f:
                json.dump(service_states, f, indent=2)
            
            log_message(f"Backed up {len(services)} service states")
            return True
            
        except Exception as e:
            log_message(f"Failed to backup services: {e}", "ERROR")
            return False
    
    def _backup_databases(self, module_backup_dir: Path, databases: List[Dict[str, str]]) -> bool:
        """Backup databases to the module backup directory."""
        if not databases:
            return True
        
        db_dir = module_backup_dir / "databases"
        db_dir.mkdir(parents=True, exist_ok=True)
        
        success_count = 0
        
        for i, db_config in enumerate(databases):
            db_type = db_config.get("type", "postgresql")
            
            try:
                if db_type == "postgresql":
                    backup_file = db_dir / f"db_{i}.sql"
                    cmd = [
                        "pg_dump",
                        "-h", db_config.get("host", "localhost"),
                        "-p", db_config.get("port", "5432"),
                        "-U", db_config.get("user", "postgres"),
                        "-d", db_config["database"],
                        "-f", str(backup_file)
                    ]
                    
                    # Set password via environment if provided
                    env = os.environ.copy()
                    if "password" in db_config:
                        env["PGPASSWORD"] = db_config["password"]
                    
                    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
                    if result.returncode != 0:
                        raise Exception(f"Database dump failed: {result.stderr}")
                
                elif db_type == "sqlite":
                    backup_file = db_dir / f"db_{i}.sqlite"
                    db_file = Path(db_config["database"])
                    shutil.copy2(db_file, backup_file)
                
                else:
                    log_message(f"Unsupported database type: {db_type}", "WARNING")
                    continue
                
                success_count += 1
                log_message(f"Backed up database {i} ({db_type})")
                
            except Exception as e:
                log_message(f"Failed to backup database {i}: {e}", "WARNING")
        
        return success_count > 0
    
    def backup_module_state(self, module_name: str, description: str = "",
                           files: List[str] = None, 
                           services: List[str] = None,
                           databases: List[Dict[str, str]] = None) -> bool:
        """
        Create a backup of the module's complete state.
        Clobbers any existing backup for this module.
        
        Args:
            module_name: Name of the module
            description: Description of the backup
            files: List of file/directory paths to backup
            services: List of service names to backup
            databases: List of database configurations to backup
            
        Returns:
            bool: True if backup successful, False otherwise
        """
        files = files or []
        services = services or []
        databases = databases or []
        
        if not files and not services and not databases:
            log_message(f"No backup data specified for module {module_name}", "WARNING")
            return False
        
        module_backup_dir = self._get_module_backup_dir(module_name)
        
        try:
            # Remove existing backup directory (clobber previous backup)
            if module_backup_dir.exists():
                shutil.rmtree(module_backup_dir)
                log_message(f"Clobbered previous backup for module {module_name}")
            
            # Create fresh backup directory
            module_backup_dir.mkdir(parents=True, exist_ok=True)
            
            # Backup each component
            files_success = self._backup_files(module_backup_dir, files) if files else True
            services_success = self._backup_services(module_backup_dir, services) if services else True
            databases_success = self._backup_databases(module_backup_dir, databases) if databases else True
            
            if not (files_success and services_success and databases_success):
                log_message(f"Some backup operations failed for module {module_name}", "WARNING")
            
            # Capture file permissions
            log_message("Capturing file permissions...")
            file_permissions = self._capture_permissions(files)
            
            # Calculate checksum of entire backup directory
            checksum = self._calculate_checksum(str(module_backup_dir))
            
            # Create backup info
            backup_info = ModuleBackupInfo(
                module_name=module_name,
                timestamp=int(time.time()),
                description=description or f"backup_{int(time.time())}",
                backup_dir=str(module_backup_dir),
                files=files,
                services=services,
                databases=databases,
                checksum=checksum,
                file_permissions=file_permissions
            )
            
            # Update index
            module_backups = self._load_module_index()
            module_backups[module_name] = backup_info
            self._save_module_index(module_backups)
            
            log_message(f"Successfully created backup for module {module_name}")
            log_message(f"  Files: {len(files)}, Services: {len(services)}, Databases: {len(databases)}")
            
            return True
            
        except Exception as e:
            log_message(f"Failed to create backup for module {module_name}: {e}", "ERROR")
            
            # Clean up partial backup
            if module_backup_dir.exists():
                try:
                    shutil.rmtree(module_backup_dir)
                except Exception:
                    pass
            
            return False
    
    def _restore_files(self, module_backup_dir: Path, files: List[str]) -> bool:
        """Restore files from the module backup directory."""
        files_dir = module_backup_dir / "files"
        
        if not files_dir.exists():
            return True  # No files to restore
        
        success_count = 0
        
        for file_path in files:
            try:
                # Determine backup location
                source = Path(file_path)
                if source.is_absolute():
                    rel_path = str(source).lstrip('/')
                else:
                    rel_path = str(source)
                
                backup_source = files_dir / rel_path
                
                if not backup_source.exists():
                    log_message(f"Backup file not found, skipping: {file_path}", "WARNING")
                    continue
                
                # Remove existing target
                if source.exists():
                    if source.is_dir():
                        shutil.rmtree(source)
                    else:
                        source.unlink()
                
                # Restore from backup
                source.parent.mkdir(parents=True, exist_ok=True)
                
                if backup_source.is_dir():
                    shutil.copytree(backup_source, source)
                else:
                    shutil.copy2(backup_source, source)
                
                success_count += 1
                log_message(f"Restored: {file_path}")
                
            except Exception as e:
                log_message(f"Failed to restore {file_path}: {e}", "WARNING")
        
        return success_count > 0 or len(files) == 0
    
    def _restore_services(self, module_backup_dir: Path, services: List[str]) -> bool:
        """Restore service states from the module backup directory."""
        if not services:
            return True
        
        services_file = module_backup_dir / "services.json"
        
        if not services_file.exists():
            log_message("No service backup found", "WARNING")
            return False
        
        try:
            with open(services_file, 'r') as f:
                service_states = json.load(f)
            
            success_count = 0
            
            # Stop all services first
            for service in services:
                try:
                    subprocess.run(["systemctl", "stop", service], check=True, capture_output=True)
                except subprocess.CalledProcessError:
                    pass  # Continue even if stop fails
            
            # Restore states
            for service in services:
                if service not in service_states:
                    log_message(f"No backup state found for service {service}", "WARNING")
                    continue
                
                state = service_states[service]
                
                try:
                    # Restore enabled/disabled state
                    if state.get("enabled", False):
                        subprocess.run(["systemctl", "enable", service], check=True, capture_output=True)
                    else:
                        subprocess.run(["systemctl", "disable", service], check=True, capture_output=True)
                    
                    # Restore active/inactive state
                    if state.get("active", False):
                        subprocess.run(["systemctl", "start", service], check=True, capture_output=True)
                    else:
                        subprocess.run(["systemctl", "stop", service], check=True, capture_output=True)
                    
                    success_count += 1
                    log_message(f"Restored service: {service}")
                    
                except subprocess.CalledProcessError as e:
                    log_message(f"Failed to restore service {service}: {e}", "WARNING")
            
            log_message(f"Restored {success_count}/{len(services)} services")
            return success_count > 0
            
        except Exception as e:
            log_message(f"Failed to restore services: {e}", "ERROR")
            return False
    
    def _restore_databases(self, module_backup_dir: Path, databases: List[Dict[str, str]]) -> bool:
        """Restore databases from the module backup directory."""
        if not databases:
            return True
        
        db_dir = module_backup_dir / "databases"
        
        if not db_dir.exists():
            log_message("No database backups found", "WARNING")
            return False
        
        success_count = 0
        
        for i, db_config in enumerate(databases):
            db_type = db_config.get("type", "postgresql")
            
            try:
                if db_type == "postgresql":
                    backup_file = db_dir / f"db_{i}.sql"
                    
                    if not backup_file.exists():
                        log_message(f"Database backup file not found: {backup_file}", "WARNING")
                        continue
                    
                    # Drop and recreate database
                    cmd_drop = [
                        "dropdb",
                        "-h", db_config.get("host", "localhost"),
                        "-p", db_config.get("port", "5432"),
                        "-U", db_config.get("user", "postgres"),
                        "--if-exists",
                        db_config["database"]
                    ]
                    
                    cmd_create = [
                        "createdb",
                        "-h", db_config.get("host", "localhost"),
                        "-p", db_config.get("port", "5432"),
                        "-U", db_config.get("user", "postgres"),
                        db_config["database"]
                    ]
                    
                    cmd_restore = [
                        "psql",
                        "-h", db_config.get("host", "localhost"),
                        "-p", db_config.get("port", "5432"),
                        "-U", db_config.get("user", "postgres"),
                        "-d", db_config["database"],
                        "-f", str(backup_file)
                    ]
                    
                    env = os.environ.copy()
                    # Note: password would need to be provided separately for security
                    
                    # Execute restoration
                    subprocess.run(cmd_drop, env=env, check=False)  # Don't fail if DB doesn't exist
                    subprocess.run(cmd_create, env=env, check=True)
                    subprocess.run(cmd_restore, env=env, check=True)
                
                elif db_type == "sqlite":
                    backup_file = db_dir / f"db_{i}.sqlite"
                    
                    if not backup_file.exists():
                        log_message(f"Database backup file not found: {backup_file}", "WARNING")
                        continue
                    
                    # For SQLite, replace the database file
                    target_path = Path(db_config["database"])
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(backup_file, target_path)
                
                else:
                    log_message(f"Unsupported database type: {db_type}", "WARNING")
                    continue
                
                success_count += 1
                log_message(f"Restored database {i} ({db_type})")
                
            except Exception as e:
                log_message(f"Failed to restore database {i}: {e}", "WARNING")
        
        log_message(f"Restored {success_count}/{len(databases)} databases")
        return success_count > 0
    
    def restore_module_state(self, module_name: str) -> bool:
        """
        Restore a module's complete state from its backup.
        
        Args:
            module_name: Name of the module to restore
            
        Returns:
            bool: True if restore successful, False otherwise
        """
        module_backups = self._load_module_index()
        
        if module_name not in module_backups:
            log_message(f"No backup found for module: {module_name}", "ERROR")
            return False
        
        backup_info = module_backups[module_name]
        module_backup_dir = Path(backup_info.backup_dir)
        
        if not module_backup_dir.exists():
            log_message(f"Backup directory not found: {module_backup_dir}", "ERROR")
            return False
        
        try:
            log_message(f"Restoring module state: {module_name}")
            
            # Restore in specific order: stop services, restore files/databases, restore services
            services_success = True
            if backup_info.services:
                # Stop services first
                for service in backup_info.services:
                    try:
                        subprocess.run(["systemctl", "stop", service], check=True, capture_output=True)
                    except subprocess.CalledProcessError:
                        pass
            
            # Restore files and databases
            files_success = self._restore_files(module_backup_dir, backup_info.files)
            databases_success = self._restore_databases(module_backup_dir, backup_info.databases)
            
            # Restore file permissions after files are restored
            permissions_success = True
            if hasattr(backup_info, 'file_permissions') and backup_info.file_permissions:
                log_message("Restoring file permissions...")
                permissions_success = self._restore_permissions(backup_info.file_permissions)
            else:
                log_message("No file permissions to restore (legacy backup or no permissions captured)")
            
            # Restore services last
            if backup_info.services:
                services_success = self._restore_services(module_backup_dir, backup_info.services)
            
            overall_success = files_success and services_success and databases_success and permissions_success
            
            if overall_success:
                log_message(f"Successfully restored module: {module_name}")
            else:
                log_message(f"Partial restore failure for module: {module_name}", "WARNING")
            
            return overall_success
            
        except Exception as e:
            log_message(f"Failed to restore module {module_name}: {e}", "ERROR")
            return False
    
    def has_backup(self, module_name: str) -> bool:
        """
        Check if a backup exists for the specified module.
        
        Args:
            module_name: Name of the module to check
            
        Returns:
            bool: True if backup exists, False otherwise
        """
        module_backups = self._load_module_index()
        
        if module_name not in module_backups:
            return False
        
        backup_info = module_backups[module_name]
        module_backup_dir = Path(backup_info.backup_dir)
        
        return module_backup_dir.exists()
    
    def get_backup_info(self, module_name: str) -> Optional[ModuleBackupInfo]:
        """
        Get backup information for a specific module.
        
        Args:
            module_name: Name of the module
            
        Returns:
            ModuleBackupInfo: Backup information or None if no backup exists
        """
        module_backups = self._load_module_index()
        return module_backups.get(module_name)
    
    def list_module_backups(self) -> Dict[str, ModuleBackupInfo]:
        """
        List all module backups.
        
        Returns:
            Dict[str, ModuleBackupInfo]: Mapping of module names to backup info
        """
        return self._load_module_index()
    
    def remove_module_backup(self, module_name: str) -> bool:
        """
        Remove the backup for a specific module.
        
        Args:
            module_name: Name of the module
            
        Returns:
            bool: True if removal successful, False otherwise
        """
        module_backups = self._load_module_index()
        
        if module_name not in module_backups:
            log_message(f"No backup found for module: {module_name}", "WARNING")
            return False
        
        backup_info = module_backups[module_name]
        module_backup_dir = Path(backup_info.backup_dir)
        
        try:
            # Remove backup directory
            if module_backup_dir.exists():
                shutil.rmtree(module_backup_dir)
            
            # Remove from index
            del module_backups[module_name]
            self._save_module_index(module_backups)
            
            log_message(f"Removed backup for module: {module_name}")
            return True
            
        except Exception as e:
            log_message(f"Failed to remove backup for module {module_name}: {e}", "ERROR")
            return False

# Convenience functions for easy import
def create_state_manager(backup_dir: str = "/var/backups/updates") -> StateManager:
    """Create a StateManager instance."""
    return StateManager(backup_dir)

def backup_module_simple(module_name: str, files: List[str] = None, 
                        services: List[str] = None, 
                        databases: List[Dict[str, str]] = None) -> bool:
    """Simple module backup function."""
    state_manager = StateManager()
    return state_manager.backup_module_state(module_name, files=files, services=services, databases=databases)

def restore_module_simple(module_name: str) -> bool:
    """Simple module restore function."""
    state_manager = StateManager()
    return state_manager.restore_module_state(module_name) 