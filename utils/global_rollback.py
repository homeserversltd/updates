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
Global Rollback Utility for Updates System

This module provides comprehensive rollback capabilities that can be used
across all update modules. It extracts and generalizes the advanced rollback
features from the hotfix system.

Key Features:
- File and directory backup/restore with checksums
- Service state capture and restoration
- Database backup and restore (PostgreSQL, SQLite)
- System state snapshots
- Atomic operation groups with rollback on failure
- Emergency standalone rollback capabilities
- Version-aware rollback using Git tags

Usage:
    from initialization.files.user_local_lib.updates.utils import GlobalRollback
    
    rollback = GlobalRollback("/var/backups/updates")
    
    # Create backups before operations
    file_backup = rollback.backup_file("/etc/config.conf", "pre_update")
    service_backup = rollback.backup_services(["nginx", "postgresql"], "pre_update")
    
    # Perform operations...
    
    # Restore if needed
    rollback.restore_backup(file_backup.backup_id)
    rollback.restore_backup(service_backup.backup_id)
"""

import os
import json
import shutil
import subprocess
import time
import hashlib
import tempfile
from pathlib import Path
from typing import Dict, List, Any, Optional, Union, Tuple
from dataclasses import dataclass, asdict
from .index import log_message

class GlobalRollbackError(Exception):
    """Custom exception for global rollback operation failures."""
    pass

@dataclass
class BackupInfo:
    """Information about a created backup."""
    backup_id: str
    timestamp: int
    backup_type: str  # 'file', 'service', 'database', 'system'
    description: str
    source_path: str
    backup_path: str
    metadata: Dict[str, Any]
    checksum: str
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BackupInfo':
        return cls(**data)

@dataclass
class RollbackOperation:
    """Represents a rollback operation."""
    operation_id: str
    operation_type: str  # 'file_restore', 'service_restore', 'db_restore', 'execute_script'
    backup_info: Optional[BackupInfo]
    rollback_script: Optional[str]
    dependencies: List[str]
    critical: bool
    metadata: Dict[str, Any]

class GlobalRollback:
    """
    Global rollback utility for the updates system.
    
    Provides comprehensive backup and rollback capabilities that can be used
    by any update module.
    """
    
    def __init__(self, backup_dir: str = "/var/backups/updates"):
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.backups_index = self.backup_dir / "backups_index.json"
        self.operations_log = self.backup_dir / "operations.log"
        
    def _generate_backup_id(self, description: str) -> str:
        """Generate unique backup ID."""
        timestamp = str(int(time.time()))
        content = f"{description}_{timestamp}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
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
    
    def _load_backups_index(self) -> Dict[str, BackupInfo]:
        """Load existing backups index."""
        if not self.backups_index.exists():
            return {}
        
        try:
            with open(self.backups_index, 'r') as f:
                data = json.load(f)
                return {
                    bid: BackupInfo.from_dict(backup_data)
                    for bid, backup_data in data.items()
                }
        except Exception as e:
            log_message(f"Failed to load backups index: {e}", "WARNING")
            return {}
    
    def _save_backups_index(self, backups: Dict[str, BackupInfo]) -> None:
        """Save backups index to disk."""
        try:
            data = {bid: backup.to_dict() for bid, backup in backups.items()}
            with open(self.backups_index, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            log_message(f"Failed to save backups index: {e}", "ERROR")
    
    def _log_operation(self, operation: str, details: Dict[str, Any]) -> None:
        """Log an operation to the operations log."""
        try:
            log_entry = {
                "timestamp": int(time.time()),
                "operation": operation,
                "details": details
            }
            
            with open(self.operations_log, 'a') as f:
                f.write(json.dumps(log_entry) + '\n')
        except Exception as e:
            log_message(f"Failed to log operation: {e}", "WARNING")
    
    def backup_file(self, source_path: str, description: str, 
                   module_name: str = "unknown") -> BackupInfo:
        """
        Create a backup of a file or directory.
        
        Args:
            source_path: Path to file or directory to backup
            description: Description of the backup
            module_name: Name of the module creating the backup
            
        Returns:
            BackupInfo: Information about the created backup
        """
        source = Path(source_path)
        if not source.exists():
            raise GlobalRollbackError(f"Source path does not exist: {source_path}")
        
        backup_id = self._generate_backup_id(f"file_{description}")
        backup_path = self.backup_dir / f"{backup_id}_{source.name}"
        
        try:
            if source.is_dir():
                shutil.copytree(source, backup_path)
            else:
                shutil.copy2(source, backup_path)
            
            checksum = self._calculate_checksum(str(backup_path))
            
            backup_info = BackupInfo(
                backup_id=backup_id,
                timestamp=int(time.time()),
                backup_type="file",
                description=description,
                source_path=str(source),
                backup_path=str(backup_path),
                metadata={
                    "module_name": module_name,
                    "is_directory": source.is_dir(),
                    "size": backup_path.stat().st_size if backup_path.is_file() else 0,
                    "permissions": oct(source.stat().st_mode)[-3:]
                },
                checksum=checksum
            )
            
            # Update index
            backups = self._load_backups_index()
            backups[backup_id] = backup_info
            self._save_backups_index(backups)
            
            # Log operation
            self._log_operation("backup_file", {
                "backup_id": backup_id,
                "source_path": source_path,
                "module_name": module_name
            })
            
            log_message(f"Created file backup: {source_path} → {backup_id}")
            return backup_info
            
        except Exception as e:
            raise GlobalRollbackError(f"Failed to backup file {source_path}: {e}")
    
    def backup_services(self, services: List[str], description: str,
                       module_name: str = "unknown") -> BackupInfo:
        """
        Create a backup of service states.
        
        Args:
            services: List of service names to backup
            description: Description of the backup
            module_name: Name of the module creating the backup
            
        Returns:
            BackupInfo: Information about the created backup
        """
        backup_id = self._generate_backup_id(f"services_{description}")
        backup_path = self.backup_dir / f"{backup_id}_services.json"
        
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
                    "enabled": is_enabled,
                    "status_output": result.stdout.strip()
                }
            
            # Save service states
            with open(backup_path, 'w') as f:
                json.dump(service_states, f, indent=2)
            
            checksum = self._calculate_checksum(str(backup_path))
            
            backup_info = BackupInfo(
                backup_id=backup_id,
                timestamp=int(time.time()),
                backup_type="service",
                description=description,
                source_path=",".join(services),
                backup_path=str(backup_path),
                metadata={
                    "module_name": module_name,
                    "services": services,
                    "service_count": len(services)
                },
                checksum=checksum
            )
            
            # Update index
            backups = self._load_backups_index()
            backups[backup_id] = backup_info
            self._save_backups_index(backups)
            
            # Log operation
            self._log_operation("backup_services", {
                "backup_id": backup_id,
                "services": services,
                "module_name": module_name
            })
            
            log_message(f"Created service backup: {services} → {backup_id}")
            return backup_info
            
        except Exception as e:
            raise GlobalRollbackError(f"Failed to backup services {services}: {e}")
    
    def backup_database(self, db_config: Dict[str, str], description: str,
                       module_name: str = "unknown") -> BackupInfo:
        """
        Create a backup of a database.
        
        Args:
            db_config: Database configuration dict with keys:
                      - type: 'postgresql' or 'sqlite'
                      - host, port, user, password, database (for PostgreSQL)
                      - database: path to database file (for SQLite)
            description: Description of the backup
            module_name: Name of the module creating the backup
            
        Returns:
            BackupInfo: Information about the created backup
        """
        backup_id = self._generate_backup_id(f"db_{description}")
        db_type = db_config.get("type", "postgresql")
        
        if db_type == "postgresql":
            backup_path = self.backup_dir / f"{backup_id}_db.sql"
        elif db_type == "sqlite":
            backup_path = self.backup_dir / f"{backup_id}_db.sqlite"
        else:
            raise GlobalRollbackError(f"Unsupported database type: {db_type}")
        
        try:
            if db_type == "postgresql":
                cmd = [
                    "pg_dump",
                    "-h", db_config.get("host", "localhost"),
                    "-p", db_config.get("port", "5432"),
                    "-U", db_config.get("user", "postgres"),
                    "-d", db_config["database"],
                    "-f", str(backup_path)
                ]
                
                # Set password via environment if provided
                env = os.environ.copy()
                if "password" in db_config:
                    env["PGPASSWORD"] = db_config["password"]
                
                result = subprocess.run(cmd, env=env, capture_output=True, text=True)
                if result.returncode != 0:
                    raise GlobalRollbackError(f"Database dump failed: {result.stderr}")
            
            elif db_type == "sqlite":
                # For SQLite, copy the database file
                db_file = Path(db_config["database"])
                shutil.copy2(db_file, backup_path)
            
            checksum = self._calculate_checksum(str(backup_path))
            
            backup_info = BackupInfo(
                backup_id=backup_id,
                timestamp=int(time.time()),
                backup_type="database",
                description=description,
                source_path=db_config.get("database", ""),
                backup_path=str(backup_path),
                metadata={
                    "module_name": module_name,
                    "db_type": db_type,
                    "db_config": {k: v for k, v in db_config.items() if k != "password"},
                    "size": backup_path.stat().st_size
                },
                checksum=checksum
            )
            
            # Update index
            backups = self._load_backups_index()
            backups[backup_id] = backup_info
            self._save_backups_index(backups)
            
            # Log operation
            self._log_operation("backup_database", {
                "backup_id": backup_id,
                "db_type": db_type,
                "database": db_config.get("database", ""),
                "module_name": module_name
            })
            
            log_message(f"Created database backup: {db_config.get('database', '')} → {backup_id}")
            return backup_info
            
        except Exception as e:
            raise GlobalRollbackError(f"Failed to backup database: {e}")
    
    def restore_backup(self, backup_id: str) -> bool:
        """
        Restore a backup by its ID.
        
        Args:
            backup_id: ID of the backup to restore
            
        Returns:
            bool: True if restore successful, False otherwise
        """
        backups = self._load_backups_index()
        
        if backup_id not in backups:
            log_message(f"Backup not found: {backup_id}", "ERROR")
            return False
        
        backup_info = backups[backup_id]
        
        try:
            if backup_info.backup_type == "file":
                return self._restore_file_backup(backup_info)
            elif backup_info.backup_type == "service":
                return self._restore_service_backup(backup_info)
            elif backup_info.backup_type == "database":
                return self._restore_database_backup(backup_info)
            else:
                log_message(f"Unknown backup type: {backup_info.backup_type}", "ERROR")
                return False
                
        except Exception as e:
            log_message(f"Failed to restore backup {backup_id}: {e}", "ERROR")
            return False
    
    def _restore_file_backup(self, backup_info: BackupInfo) -> bool:
        """Restore a file backup."""
        source_path = Path(backup_info.backup_path)
        target_path = Path(backup_info.source_path)
        
        if not source_path.exists():
            log_message(f"Backup file not found: {source_path}", "ERROR")
            return False
        
        try:
            # Remove existing target
            if target_path.exists():
                if target_path.is_dir():
                    shutil.rmtree(target_path)
                else:
                    target_path.unlink()
            
            # Restore from backup
            target_path.parent.mkdir(parents=True, exist_ok=True)
            
            if backup_info.metadata.get("is_directory", False):
                shutil.copytree(source_path, target_path)
            else:
                shutil.copy2(source_path, target_path)
            
            # Restore permissions if available
            if "permissions" in backup_info.metadata:
                try:
                    os.chmod(target_path, int(backup_info.metadata["permissions"], 8))
                except Exception as e:
                    log_message(f"Failed to restore permissions: {e}", "WARNING")
            
            # Log operation
            self._log_operation("restore_file", {
                "backup_id": backup_info.backup_id,
                "target_path": str(target_path)
            })
            
            log_message(f"Restored file backup: {backup_info.backup_id} → {target_path}")
            return True
            
        except Exception as e:
            log_message(f"Failed to restore file backup: {e}", "ERROR")
            return False
    
    def _restore_service_backup(self, backup_info: BackupInfo) -> bool:
        """Restore a service backup."""
        backup_path = Path(backup_info.backup_path)
        
        if not backup_path.exists():
            log_message(f"Service backup not found: {backup_path}", "ERROR")
            return False
        
        try:
            with open(backup_path, 'r') as f:
                service_states = json.load(f)
            
            success_count = 0
            for service, state in service_states.items():
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
                    
                    log_message(f"Restored service state: {service}")
                    success_count += 1
                    
                except subprocess.CalledProcessError as e:
                    log_message(f"Failed to restore service {service}: {e}", "WARNING")
            
            # Log operation
            self._log_operation("restore_services", {
                "backup_id": backup_info.backup_id,
                "services_restored": success_count,
                "total_services": len(service_states)
            })
            
            log_message(f"Restored service backup: {backup_info.backup_id} ({success_count}/{len(service_states)} services)")
            return success_count > 0
            
        except Exception as e:
            log_message(f"Failed to restore service backup: {e}", "ERROR")
            return False
    
    def _restore_database_backup(self, backup_info: BackupInfo) -> bool:
        """Restore a database backup."""
        backup_path = Path(backup_info.backup_path)
        db_type = backup_info.metadata.get("db_type", "postgresql")
        db_config = backup_info.metadata.get("db_config", {})
        
        if not backup_path.exists():
            log_message(f"Database backup not found: {backup_path}", "ERROR")
            return False
        
        try:
            if db_type == "postgresql":
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
                    "-f", str(backup_path)
                ]
                
                env = os.environ.copy()
                # Note: password would need to be provided separately for security
                
                # Execute restoration
                subprocess.run(cmd_drop, env=env, check=False)  # Don't fail if DB doesn't exist
                subprocess.run(cmd_create, env=env, check=True)
                subprocess.run(cmd_restore, env=env, check=True)
                
            elif db_type == "sqlite":
                # For SQLite, replace the database file
                target_path = Path(backup_info.source_path)
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup_path, target_path)
            
            # Log operation
            self._log_operation("restore_database", {
                "backup_id": backup_info.backup_id,
                "db_type": db_type,
                "database": backup_info.source_path
            })
            
            log_message(f"Restored database backup: {backup_info.backup_id}")
            return True
            
        except Exception as e:
            log_message(f"Failed to restore database backup: {e}", "ERROR")
            return False
    
    def list_backups(self, module_name: Optional[str] = None,
                    backup_type: Optional[str] = None) -> List[BackupInfo]:
        """
        List available backups with optional filtering.
        
        Args:
            module_name: Filter by module name
            backup_type: Filter by backup type ('file', 'service', 'database')
            
        Returns:
            List[BackupInfo]: List of matching backups
        """
        backups = self._load_backups_index()
        backup_list = list(backups.values())
        
        # Apply filters
        if module_name:
            backup_list = [b for b in backup_list 
                          if b.metadata.get("module_name") == module_name]
        
        if backup_type:
            backup_list = [b for b in backup_list if b.backup_type == backup_type]
        
        # Sort by timestamp (newest first)
        backup_list.sort(key=lambda b: b.timestamp, reverse=True)
        
        return backup_list
    
    def cleanup_old_backups(self, max_age_days: int = 30,
                           keep_minimum: int = 5) -> int:
        """
        Remove old backups while keeping a minimum number.
        
        Args:
            max_age_days: Maximum age in days for backups
            keep_minimum: Minimum number of backups to keep per module
            
        Returns:
            int: Number of backups removed
        """
        cutoff_time = int(time.time()) - (max_age_days * 24 * 60 * 60)
        backups = self._load_backups_index()
        
        # Group backups by module
        module_backups = {}
        for backup_id, backup_info in backups.items():
            module_name = backup_info.metadata.get("module_name", "unknown")
            if module_name not in module_backups:
                module_backups[module_name] = []
            module_backups[module_name].append((backup_id, backup_info))
        
        removed_count = 0
        
        for module_name, module_backup_list in module_backups.items():
            # Sort by timestamp (newest first)
            module_backup_list.sort(key=lambda x: x[1].timestamp, reverse=True)
            
            # Keep minimum number of backups
            backups_to_check = module_backup_list[keep_minimum:]
            
            for backup_id, backup_info in backups_to_check:
                if backup_info.timestamp < cutoff_time:
                    try:
                        # Remove backup data
                        backup_path = Path(backup_info.backup_path)
                        if backup_path.exists():
                            if backup_path.is_dir():
                                shutil.rmtree(backup_path)
                            else:
                                backup_path.unlink()
                        
                        # Remove from index
                        del backups[backup_id]
                        removed_count += 1
                        
                        log_message(f"Removed old backup: {backup_id} ({module_name})")
                        
                    except Exception as e:
                        log_message(f"Failed to remove backup {backup_id}: {e}", "WARNING")
        
        # Save updated index
        self._save_backups_index(backups)
        
        log_message(f"Cleaned up {removed_count} old backups")
        return removed_count
    
    def create_rollback_point(self, module_name: str, description: str,
                             files: List[str] = None,
                             services: List[str] = None,
                             databases: List[Dict[str, str]] = None) -> Dict[str, str]:
        """
        Create a comprehensive rollback point for a module.
        
        Args:
            module_name: Name of the module
            description: Description of the rollback point
            files: List of file paths to backup
            services: List of service names to backup
            databases: List of database configurations to backup
            
        Returns:
            Dict[str, str]: Mapping of backup types to backup IDs
        """
        rollback_point = {}
        
        try:
            if files:
                for file_path in files:
                    try:
                        backup_info = self.backup_file(file_path, description, module_name)
                        rollback_point[f"file_{Path(file_path).name}"] = backup_info.backup_id
                    except Exception as e:
                        log_message(f"Failed to backup file {file_path}: {e}", "WARNING")
            
            if services:
                try:
                    backup_info = self.backup_services(services, description, module_name)
                    rollback_point["services"] = backup_info.backup_id
                except Exception as e:
                    log_message(f"Failed to backup services: {e}", "WARNING")
            
            if databases:
                for i, db_config in enumerate(databases):
                    try:
                        backup_info = self.backup_database(db_config, description, module_name)
                        rollback_point[f"database_{i}"] = backup_info.backup_id
                    except Exception as e:
                        log_message(f"Failed to backup database {i}: {e}", "WARNING")
            
            log_message(f"Created rollback point for {module_name}: {len(rollback_point)} backups")
            return rollback_point
            
        except Exception as e:
            log_message(f"Failed to create rollback point for {module_name}: {e}", "ERROR")
            return rollback_point
    
    def restore_rollback_point(self, rollback_point: Dict[str, str]) -> bool:
        """
        Restore all backups in a rollback point.
        
        Args:
            rollback_point: Dict mapping backup types to backup IDs
            
        Returns:
            bool: True if all restores successful, False otherwise
        """
        success_count = 0
        total_count = len(rollback_point)
        
        # Restore in specific order: services first (stop), then files, then databases, then services (start)
        service_backup_id = rollback_point.get("services")
        
        # Stop services first if we have a service backup
        if service_backup_id:
            backups = self._load_backups_index()
            if service_backup_id in backups:
                backup_info = backups[service_backup_id]
                try:
                    with open(backup_info.backup_path, 'r') as f:
                        service_states = json.load(f)
                    
                    # Stop all services first
                    for service in service_states.keys():
                        try:
                            subprocess.run(["systemctl", "stop", service], check=True, capture_output=True)
                        except subprocess.CalledProcessError:
                            pass  # Continue even if stop fails
                except Exception:
                    pass
        
        # Restore files and databases
        for backup_type, backup_id in rollback_point.items():
            if backup_type != "services":  # Handle services separately
                if self.restore_backup(backup_id):
                    success_count += 1
                else:
                    log_message(f"Failed to restore backup: {backup_id}", "ERROR")
        
        # Restore services last
        if service_backup_id:
            if self.restore_backup(service_backup_id):
                success_count += 1
            else:
                log_message(f"Failed to restore services backup: {service_backup_id}", "ERROR")
        
        log_message(f"Restored rollback point: {success_count}/{total_count} backups successful")
        return success_count == total_count

# Convenience functions for easy import
def create_global_rollback(backup_dir: str = "/var/backups/updates") -> GlobalRollback:
    """Create a GlobalRollback instance."""
    return GlobalRollback(backup_dir)

def backup_file_simple(source_path: str, description: str, module_name: str = "unknown") -> str:
    """Simple file backup function that returns backup ID."""
    rollback = GlobalRollback()
    backup_info = rollback.backup_file(source_path, description, module_name)
    return backup_info.backup_id

def restore_backup_simple(backup_id: str) -> bool:
    """Simple restore function."""
    rollback = GlobalRollback()
    return rollback.restore_backup(backup_id) 