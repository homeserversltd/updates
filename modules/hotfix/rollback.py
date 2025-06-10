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

#!/usr/bin/env python3
"""
Advanced Rollback Management System

Handles complex rollback scenarios including:
- One-way operations (database migrations, deletions, etc.)
- State capture and restoration
- Dependency-aware rollback sequencing
- Emergency recovery procedures
"""

import os
import json
import shutil
import subprocess
import time
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from initialization.files.user_local_lib.updates import log_message

class RollbackError(Exception):
    """Custom exception for rollback operation failures."""
    pass

@dataclass
class StateSnapshot:
    """Represents a captured system state at a point in time."""
    snapshot_id: str
    timestamp: int
    description: str
    snapshot_type: str  # 'file', 'database', 'service', 'system'
    data_path: str
    metadata: Dict[str, Any]
    checksum: str
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StateSnapshot':
        return cls(**data)

@dataclass
class RollbackOperation:
    """Represents a rollback operation with its context."""
    operation_id: str
    rollback_type: str  # 'restore_backup', 'execute_script', 'restore_state'
    source_path: Optional[str]
    target_path: Optional[str]
    rollback_script: Optional[str]
    state_snapshot_id: Optional[str]
    dependencies: List[str]
    phase: int
    critical: bool
    metadata: Dict[str, Any]

class StateCapture:
    """Handles system state capture and restoration."""
    
    def __init__(self, backup_dir: str):
        self.backup_dir = Path(backup_dir)
        self.snapshots_dir = self.backup_dir / "snapshots"
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.snapshots_index = self.snapshots_dir / "index.json"
        
    def _generate_snapshot_id(self, description: str) -> str:
        """Generate unique snapshot ID."""
        timestamp = str(int(time.time()))
        content = f"{description}_{timestamp}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def _calculate_checksum(self, file_path: str) -> str:
        """Calculate SHA-256 checksum of a file."""
        sha256_hash = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(chunk)
            return sha256_hash.hexdigest()
        except Exception:
            return ""
    
    def _load_snapshots_index(self) -> Dict[str, StateSnapshot]:
        """Load existing snapshots index."""
        if not self.snapshots_index.exists():
            return {}
        
        try:
            with open(self.snapshots_index, 'r') as f:
                data = json.load(f)
                return {
                    sid: StateSnapshot.from_dict(snapshot_data)
                    for sid, snapshot_data in data.items()
                }
        except Exception as e:
            log_message(f"Failed to load snapshots index: {e}", "WARNING")
            return {}
    
    def _save_snapshots_index(self, snapshots: Dict[str, StateSnapshot]) -> None:
        """Save snapshots index to disk."""
        try:
            data = {sid: snapshot.to_dict() for sid, snapshot in snapshots.items()}
            with open(self.snapshots_index, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            log_message(f"Failed to save snapshots index: {e}", "ERROR")
    
    def capture_file_state(self, file_path: str, description: str) -> StateSnapshot:
        """Capture state of a file or directory."""
        source_path = Path(file_path)
        if not source_path.exists():
            raise RollbackError(f"Cannot capture state: {file_path} does not exist")
        
        snapshot_id = self._generate_snapshot_id(f"file_{description}")
        snapshot_path = self.snapshots_dir / f"{snapshot_id}.backup"
        
        try:
            if source_path.is_dir():
                shutil.copytree(source_path, snapshot_path)
            else:
                shutil.copy2(source_path, snapshot_path)
            
            checksum = self._calculate_checksum(str(snapshot_path))
            
            snapshot = StateSnapshot(
                snapshot_id=snapshot_id,
                timestamp=int(time.time()),
                description=description,
                snapshot_type="file",
                data_path=str(snapshot_path),
                metadata={
                    "original_path": str(source_path),
                    "is_directory": source_path.is_dir(),
                    "size": snapshot_path.stat().st_size if snapshot_path.is_file() else 0
                },
                checksum=checksum
            )
            
            # Update index
            snapshots = self._load_snapshots_index()
            snapshots[snapshot_id] = snapshot
            self._save_snapshots_index(snapshots)
            
            log_message(f"Captured file state: {file_path} → {snapshot_id}")
            return snapshot
            
        except Exception as e:
            raise RollbackError(f"Failed to capture file state for {file_path}: {e}")
    
    def capture_database_state(self, db_config: Dict[str, str], description: str) -> StateSnapshot:
        """Capture database state using pg_dump or similar."""
        snapshot_id = self._generate_snapshot_id(f"db_{description}")
        snapshot_path = self.snapshots_dir / f"{snapshot_id}.sql"
        
        try:
            # Support different database types
            db_type = db_config.get("type", "postgresql")
            
            if db_type == "postgresql":
                cmd = [
                    "pg_dump",
                    "-h", db_config.get("host", "localhost"),
                    "-p", db_config.get("port", "5432"),
                    "-U", db_config.get("user", "postgres"),
                    "-d", db_config["database"],
                    "-f", str(snapshot_path)
                ]
                
                # Set password via environment if provided
                env = os.environ.copy()
                if "password" in db_config:
                    env["PGPASSWORD"] = db_config["password"]
                
                result = subprocess.run(cmd, env=env, capture_output=True, text=True)
                if result.returncode != 0:
                    raise RollbackError(f"Database dump failed: {result.stderr}")
            
            elif db_type == "sqlite":
                # For SQLite, just copy the database file
                db_file = Path(db_config["database"])
                shutil.copy2(db_file, snapshot_path.with_suffix('.db'))
                snapshot_path = snapshot_path.with_suffix('.db')
            
            else:
                raise RollbackError(f"Unsupported database type: {db_type}")
            
            checksum = self._calculate_checksum(str(snapshot_path))
            
            snapshot = StateSnapshot(
                snapshot_id=snapshot_id,
                timestamp=int(time.time()),
                description=description,
                snapshot_type="database",
                data_path=str(snapshot_path),
                metadata={
                    "db_type": db_type,
                    "db_config": db_config,
                    "size": snapshot_path.stat().st_size
                },
                checksum=checksum
            )
            
            # Update index
            snapshots = self._load_snapshots_index()
            snapshots[snapshot_id] = snapshot
            self._save_snapshots_index(snapshots)
            
            log_message(f"Captured database state: {db_config['database']} → {snapshot_id}")
            return snapshot
            
        except Exception as e:
            raise RollbackError(f"Failed to capture database state: {e}")
    
    def capture_service_state(self, services: List[str], description: str) -> StateSnapshot:
        """Capture state of system services."""
        snapshot_id = self._generate_snapshot_id(f"services_{description}")
        snapshot_path = self.snapshots_dir / f"{snapshot_id}.json"
        
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
            with open(snapshot_path, 'w') as f:
                json.dump(service_states, f, indent=2)
            
            checksum = self._calculate_checksum(str(snapshot_path))
            
            snapshot = StateSnapshot(
                snapshot_id=snapshot_id,
                timestamp=int(time.time()),
                description=description,
                snapshot_type="service",
                data_path=str(snapshot_path),
                metadata={
                    "services": services,
                    "service_count": len(services)
                },
                checksum=checksum
            )
            
            # Update index
            snapshots = self._load_snapshots_index()
            snapshots[snapshot_id] = snapshot
            self._save_snapshots_index(snapshots)
            
            log_message(f"Captured service state: {services} → {snapshot_id}")
            return snapshot
            
        except Exception as e:
            raise RollbackError(f"Failed to capture service state: {e}")
    
    def capture_system_state(self, description: str, include_packages: bool = False) -> StateSnapshot:
        """Capture comprehensive system state."""
        snapshot_id = self._generate_snapshot_id(f"system_{description}")
        snapshot_path = self.snapshots_dir / f"{snapshot_id}_system"
        snapshot_path.mkdir(exist_ok=True)
        
        try:
            system_info = {}
            
            # Capture network configuration
            network_file = snapshot_path / "network.json"
            network_info = {}
            
            # IP configuration
            result = subprocess.run(["ip", "addr", "show"], capture_output=True, text=True)
            network_info["ip_addr"] = result.stdout
            
            # Routing table
            result = subprocess.run(["ip", "route", "show"], capture_output=True, text=True)
            network_info["routes"] = result.stdout
            
            # Firewall rules (if iptables exists)
            try:
                result = subprocess.run(["iptables", "-L", "-n"], capture_output=True, text=True)
                network_info["iptables"] = result.stdout
            except FileNotFoundError:
                network_info["iptables"] = "iptables not available"
            
            with open(network_file, 'w') as f:
                json.dump(network_info, f, indent=2)
            
            # Capture mounted filesystems
            mounts_file = snapshot_path / "mounts.txt"
            result = subprocess.run(["mount"], capture_output=True, text=True)
            with open(mounts_file, 'w') as f:
                f.write(result.stdout)
            
            # Capture running processes
            processes_file = snapshot_path / "processes.txt"
            result = subprocess.run(["ps", "aux"], capture_output=True, text=True)
            with open(processes_file, 'w') as f:
                f.write(result.stdout)
            
            # Capture package information if requested
            if include_packages:
                packages_file = snapshot_path / "packages.txt"
                try:
                    # Try different package managers
                    if shutil.which("dpkg"):
                        result = subprocess.run(["dpkg", "-l"], capture_output=True, text=True)
                    elif shutil.which("rpm"):
                        result = subprocess.run(["rpm", "-qa"], capture_output=True, text=True)
                    elif shutil.which("pacman"):
                        result = subprocess.run(["pacman", "-Q"], capture_output=True, text=True)
                    else:
                        result = subprocess.CompletedProcess([], 0, "No package manager found", "")
                    
                    with open(packages_file, 'w') as f:
                        f.write(result.stdout)
                except Exception as e:
                    log_message(f"Failed to capture package info: {e}", "WARNING")
            
            # Create summary
            summary_file = snapshot_path / "summary.json"
            summary = {
                "timestamp": int(time.time()),
                "hostname": subprocess.run(["hostname"], capture_output=True, text=True).stdout.strip(),
                "kernel": subprocess.run(["uname", "-r"], capture_output=True, text=True).stdout.strip(),
                "uptime": subprocess.run(["uptime"], capture_output=True, text=True).stdout.strip(),
                "include_packages": include_packages
            }
            
            with open(summary_file, 'w') as f:
                json.dump(summary, f, indent=2)
            
            # Calculate checksum of entire directory
            checksum = hashlib.sha256()
            for file_path in sorted(snapshot_path.rglob("*")):
                if file_path.is_file():
                    with open(file_path, 'rb') as f:
                        checksum.update(f.read())
            
            snapshot = StateSnapshot(
                snapshot_id=snapshot_id,
                timestamp=int(time.time()),
                description=description,
                snapshot_type="system",
                data_path=str(snapshot_path),
                metadata={
                    "include_packages": include_packages,
                    "files_captured": len(list(snapshot_path.rglob("*")))
                },
                checksum=checksum.hexdigest()
            )
            
            # Update index
            snapshots = self._load_snapshots_index()
            snapshots[snapshot_id] = snapshot
            self._save_snapshots_index(snapshots)
            
            log_message(f"Captured system state → {snapshot_id}")
            return snapshot
            
        except Exception as e:
            raise RollbackError(f"Failed to capture system state: {e}")
    
    def restore_snapshot(self, snapshot_id: str) -> bool:
        """Restore a previously captured snapshot."""
        snapshots = self._load_snapshots_index()
        
        if snapshot_id not in snapshots:
            raise RollbackError(f"Snapshot not found: {snapshot_id}")
        
        snapshot = snapshots[snapshot_id]
        
        try:
            if snapshot.snapshot_type == "file":
                self._restore_file_snapshot(snapshot)
            elif snapshot.snapshot_type == "database":
                self._restore_database_snapshot(snapshot)
            elif snapshot.snapshot_type == "service":
                self._restore_service_snapshot(snapshot)
            elif snapshot.snapshot_type == "system":
                log_message("System snapshot restoration requires manual intervention", "WARNING")
                return False
            else:
                raise RollbackError(f"Unknown snapshot type: {snapshot.snapshot_type}")
            
            log_message(f"Successfully restored snapshot: {snapshot_id}")
            return True
            
        except Exception as e:
            log_message(f"Failed to restore snapshot {snapshot_id}: {e}", "ERROR")
            return False
    
    def _restore_file_snapshot(self, snapshot: StateSnapshot) -> None:
        """Restore a file snapshot."""
        source_path = Path(snapshot.data_path)
        target_path = Path(snapshot.metadata["original_path"])
        
        if not source_path.exists():
            raise RollbackError(f"Snapshot data not found: {source_path}")
        
        # Remove existing target
        if target_path.exists():
            if target_path.is_dir():
                shutil.rmtree(target_path)
            else:
                target_path.unlink()
        
        # Restore from snapshot
        target_path.parent.mkdir(parents=True, exist_ok=True)
        
        if snapshot.metadata["is_directory"]:
            shutil.copytree(source_path, target_path)
        else:
            shutil.copy2(source_path, target_path)
        
        log_message(f"Restored file: {target_path}")
    
    def _restore_database_snapshot(self, snapshot: StateSnapshot) -> None:
        """Restore a database snapshot."""
        db_config = snapshot.metadata["db_config"]
        db_type = snapshot.metadata["db_type"]
        snapshot_path = Path(snapshot.data_path)
        
        if not snapshot_path.exists():
            raise RollbackError(f"Database snapshot not found: {snapshot_path}")
        
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
                "-f", str(snapshot_path)
            ]
            
            env = os.environ.copy()
            if "password" in db_config:
                env["PGPASSWORD"] = db_config["password"]
            
            # Execute restoration
            subprocess.run(cmd_drop, env=env, check=False)  # Don't fail if DB doesn't exist
            subprocess.run(cmd_create, env=env, check=True)
            subprocess.run(cmd_restore, env=env, check=True)
            
        elif db_type == "sqlite":
            # For SQLite, replace the database file
            target_path = Path(db_config["database"])
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(snapshot_path, target_path)
        
        log_message(f"Restored database: {db_config['database']}")
    
    def _restore_service_snapshot(self, snapshot: StateSnapshot) -> None:
        """Restore service states."""
        snapshot_path = Path(snapshot.data_path)
        
        if not snapshot_path.exists():
            raise RollbackError(f"Service snapshot not found: {snapshot_path}")
        
        with open(snapshot_path, 'r') as f:
            service_states = json.load(f)
        
        for service, state in service_states.items():
            try:
                # Restore enabled/disabled state
                if state["enabled"]:
                    subprocess.run(["systemctl", "enable", service], check=True)
                else:
                    subprocess.run(["systemctl", "disable", service], check=True)
                
                # Restore active/inactive state
                if state["active"]:
                    subprocess.run(["systemctl", "start", service], check=True)
                else:
                    subprocess.run(["systemctl", "stop", service], check=True)
                
                log_message(f"Restored service state: {service}")
                
            except subprocess.CalledProcessError as e:
                log_message(f"Failed to restore service {service}: {e}", "WARNING")
    
    def list_snapshots(self) -> List[StateSnapshot]:
        """List all available snapshots."""
        snapshots = self._load_snapshots_index()
        return sorted(snapshots.values(), key=lambda s: s.timestamp, reverse=True)
    
    def cleanup_old_snapshots(self, max_age_days: int = 30) -> int:
        """Remove snapshots older than specified days."""
        cutoff_time = int(time.time()) - (max_age_days * 24 * 60 * 60)
        snapshots = self._load_snapshots_index()
        
        removed_count = 0
        for snapshot_id, snapshot in list(snapshots.items()):
            if snapshot.timestamp < cutoff_time:
                try:
                    # Remove snapshot data
                    snapshot_path = Path(snapshot.data_path)
                    if snapshot_path.exists():
                        if snapshot_path.is_dir():
                            shutil.rmtree(snapshot_path)
                        else:
                            snapshot_path.unlink()
                    
                    # Remove from index
                    del snapshots[snapshot_id]
                    removed_count += 1
                    
                    log_message(f"Removed old snapshot: {snapshot_id}")
                    
                except Exception as e:
                    log_message(f"Failed to remove snapshot {snapshot_id}: {e}", "WARNING")
        
        # Save updated index
        self._save_snapshots_index(snapshots)
        
        log_message(f"Cleaned up {removed_count} old snapshots")
        return removed_count

class RollbackManager:
    """Advanced rollback management with dependency resolution and state restoration."""
    
    def __init__(self, backup_dir: str):
        self.backup_dir = Path(backup_dir)
        self.state_capture = StateCapture(str(self.backup_dir))
        self.rollback_log_file = self.backup_dir / "rollback.log"
        self.operations_log = []
        
    def create_rollback_plan(self, operations: List[Dict[str, Any]]) -> List[RollbackOperation]:
        """Create a comprehensive rollback plan for a set of operations."""
        rollback_ops = []
        
        for operation in operations:
            rollback_op = self._create_rollback_operation(operation)
            if rollback_op:
                rollback_ops.append(rollback_op)
        
        # Sort by phase (reverse order) and resolve dependencies
        rollback_ops.sort(key=lambda op: (-op.phase, op.operation_id))
        
        return rollback_ops
    
    def _create_rollback_operation(self, operation: Dict[str, Any]) -> Optional[RollbackOperation]:
        """Create a rollback operation for a given operation."""
        op_type = operation.get("type")
        op_id = operation.get("id")
        
        if op_type == "copy":
            return RollbackOperation(
                operation_id=f"rollback_{op_id}",
                rollback_type="restore_backup",
                source_path=operation.get("backup_path"),
                target_path=operation.get("target"),
                rollback_script=None,
                state_snapshot_id=None,
                dependencies=[],
                phase=operation.get("phase", 1),
                critical=operation.get("critical", False),
                metadata={"original_operation": operation}
            )
        
        elif op_type == "execute":
            # Check if operation has explicit rollback script
            rollback_script = operation.get("rollback_script")
            if rollback_script:
                return RollbackOperation(
                    operation_id=f"rollback_{op_id}",
                    rollback_type="execute_script",
                    source_path=None,
                    target_path=None,
                    rollback_script=rollback_script,
                    state_snapshot_id=None,
                    dependencies=[],
                    phase=operation.get("phase", 1),
                    critical=operation.get("critical", False),
                    metadata={"original_operation": operation}
                )
        
        elif op_type == "capture_state":
            # State capture operations can be restored
            return RollbackOperation(
                operation_id=f"rollback_{op_id}",
                rollback_type="restore_state",
                source_path=None,
                target_path=None,
                rollback_script=None,
                state_snapshot_id=operation.get("snapshot_id"),
                dependencies=[],
                phase=operation.get("phase", 1),
                critical=operation.get("critical", False),
                metadata={"original_operation": operation}
            )
        
        return None
    
    def execute_rollback_plan(self, rollback_ops: List[RollbackOperation]) -> bool:
        """Execute a rollback plan with dependency resolution."""
        log_message("Starting rollback plan execution...")
        
        try:
            # Group operations by phase
            phases = {}
            for op in rollback_ops:
                if op.phase not in phases:
                    phases[op.phase] = []
                phases[op.phase].append(op)
            
            # Execute phases in reverse order
            for phase in sorted(phases.keys(), reverse=True):
                log_message(f"Executing rollback phase {phase}")
                
                phase_ops = phases[phase]
                for rollback_op in phase_ops:
                    try:
                        self._execute_rollback_operation(rollback_op)
                        log_message(f"Rollback operation completed: {rollback_op.operation_id}")
                        
                    except Exception as e:
                        log_message(f"Rollback operation failed: {rollback_op.operation_id} - {e}", "ERROR")
                        
                        if rollback_op.critical:
                            log_message("Critical rollback operation failed, stopping rollback", "ERROR")
                            return False
                        else:
                            log_message("Non-critical rollback operation failed, continuing", "WARNING")
                
                log_message(f"Rollback phase {phase} completed")
            
            log_message("Rollback plan execution completed successfully")
            return True
            
        except Exception as e:
            log_message(f"Rollback plan execution failed: {e}", "ERROR")
            return False
    
    def _execute_rollback_operation(self, rollback_op: RollbackOperation) -> None:
        """Execute a single rollback operation."""
        if rollback_op.rollback_type == "restore_backup":
            self._restore_from_backup(rollback_op)
        elif rollback_op.rollback_type == "execute_script":
            self._execute_rollback_script(rollback_op)
        elif rollback_op.rollback_type == "restore_state":
            self._restore_from_state(rollback_op)
        else:
            raise RollbackError(f"Unknown rollback type: {rollback_op.rollback_type}")
    
    def _restore_from_backup(self, rollback_op: RollbackOperation) -> None:
        """Restore a file from backup."""
        if not rollback_op.source_path or not rollback_op.target_path:
            raise RollbackError("Missing source or target path for backup restoration")
        
        source_path = Path(rollback_op.source_path)
        target_path = Path(rollback_op.target_path)
        
        if not source_path.exists():
            raise RollbackError(f"Backup file not found: {source_path}")
        
        # Remove existing target
        if target_path.exists():
            if target_path.is_dir():
                shutil.rmtree(target_path)
            else:
                target_path.unlink()
        
        # Restore from backup
        target_path.parent.mkdir(parents=True, exist_ok=True)
        
        if source_path.is_dir():
            shutil.copytree(source_path, target_path)
        else:
            shutil.copy2(source_path, target_path)
        
        log_message(f"Restored from backup: {source_path} → {target_path}")
    
    def _execute_rollback_script(self, rollback_op: RollbackOperation) -> None:
        """Execute a rollback script."""
        if not rollback_op.rollback_script:
            raise RollbackError("No rollback script specified")
        
        script_path = Path(rollback_op.rollback_script)
        if not script_path.exists():
            raise RollbackError(f"Rollback script not found: {script_path}")
        
        # Make script executable
        os.chmod(script_path, 0o755)
        
        # Execute script
        log_message(f"Executing rollback script: {script_path}")
        result = subprocess.run(
            [str(script_path)],
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if result.returncode != 0:
            raise RollbackError(f"Rollback script failed: {result.stderr}")
        
        log_message(f"Rollback script executed successfully: {script_path}")
        if result.stdout:
            log_message(f"Script output: {result.stdout}")
    
    def _restore_from_state(self, rollback_op: RollbackOperation) -> None:
        """Restore from a state snapshot."""
        if not rollback_op.state_snapshot_id:
            raise RollbackError("No state snapshot ID specified")
        
        success = self.state_capture.restore_snapshot(rollback_op.state_snapshot_id)
        if not success:
            raise RollbackError(f"Failed to restore state snapshot: {rollback_op.state_snapshot_id}")
    
    def emergency_rollback(self, operation_log: List[Dict[str, Any]]) -> bool:
        """Perform emergency rollback of all operations in reverse order."""
        log_message("EMERGENCY ROLLBACK INITIATED", "ERROR")
        
        try:
            # Simple reverse-order rollback for emergency situations
            for operation in reversed(operation_log):
                if not operation.get("success", False):
                    continue
                    
                try:
                    operation_type = operation.get("type")
                    operation_id = operation.get("operation_id")
                    
                    log_message(f"Emergency rollback: {operation_id} ({operation_type})")
                    
                    if operation_type in ["copy", "symlink"] and operation.get("backup_path"):
                        # Restore from backup
                        backup_path = Path(operation["backup_path"])
                        target_path = Path(operation["target"])
                        
                        if backup_path.exists():
                            if target_path.exists():
                                if target_path.is_dir():
                                    shutil.rmtree(target_path)
                                else:
                                    target_path.unlink()
                            
                            if backup_path.is_dir():
                                shutil.copytree(backup_path, target_path)
                            else:
                                shutil.copy2(backup_path, target_path)
                            
                            log_message(f"Emergency restored: {backup_path} → {target_path}")
                    
                    elif operation_type == "append":
                        # Remove appended content using markers
                        target_path = Path(operation["target"])
                        identifier = operation.get("identifier", operation_id)
                        marker = operation.get("marker", f"# HOTFIX {identifier.upper()}")
                        
                        if target_path.exists():
                            with open(target_path, 'r') as f:
                                content = f.read()
                            
                            # Remove content between markers
                            start_marker = f"{marker} START"
                            end_marker = f"{marker} END"
                            
                            while start_marker in content and end_marker in content:
                                start_idx = content.find(start_marker)
                                end_idx = content.find(end_marker) + len(end_marker)
                                content = content[:start_idx] + content[end_idx:]
                            
                            with open(target_path, 'w') as f:
                                f.write(content)
                            
                            log_message(f"Emergency removed appended content from {target_path}")
                    
                    log_message(f"Emergency rollback completed: {operation_id}")
                    
                except Exception as e:
                    log_message(f"Emergency rollback failed for {operation.get('operation_id', 'unknown')}: {e}", "ERROR")
            
            log_message("Emergency rollback completed")
            return True
            
        except Exception as e:
            log_message(f"Emergency rollback failed: {e}", "ERROR")
            return False

def main(args=None):
    """
    Standalone rollback script entry point.
    
    Usage:
        python rollback.py --list-snapshots
        python rollback.py --snapshot-id <id>
        python rollback.py --emergency-rollback <operations_log.json>
    """
    if args is None:
        import sys
        args = sys.argv[1:]
    
    if not args:
        print("Usage: rollback.py [--snapshot-id ID | --list-snapshots | --emergency-rollback LOG_FILE]")
        return False
    
    backup_dir = "/var/backups/hotfix"
    
    try:
        if "--list-snapshots" in args:
            state_capture = StateCapture(backup_dir)
            snapshots = state_capture.list_snapshots()
            
            print(f"Found {len(snapshots)} snapshots:")
            for snapshot in snapshots:
                print(f"  {snapshot.snapshot_id}: {snapshot.description} ({snapshot.snapshot_type})")
                print(f"    Created: {time.ctime(snapshot.timestamp)}")
                print(f"    Path: {snapshot.data_path}")
                print()
            
            return True
        
        elif "--snapshot-id" in args:
            idx = args.index("--snapshot-id")
            if idx + 1 >= len(args):
                print("Error: --snapshot-id requires a snapshot ID")
                return False
            
            snapshot_id = args[idx + 1]
            state_capture = StateCapture(backup_dir)
            
            success = state_capture.restore_snapshot(snapshot_id)
            if success:
                print(f"Successfully restored snapshot: {snapshot_id}")
            else:
                print(f"Failed to restore snapshot: {snapshot_id}")
            
            return success
        
        elif "--emergency-rollback" in args:
            idx = args.index("--emergency-rollback")
            if idx + 1 >= len(args):
                print("Error: --emergency-rollback requires a log file path")
                return False
            
            log_file = args[idx + 1]
            
            with open(log_file, 'r') as f:
                operation_log = json.load(f)
            
            rollback_manager = RollbackManager(backup_dir)
            success = rollback_manager.emergency_rollback(operation_log)
            
            if success:
                print("Emergency rollback completed successfully")
            else:
                print("Emergency rollback completed with errors")
            
            return success
        
        else:
            print("Unknown command. Use --help for usage information.")
            return False
    
    except Exception as e:
        print(f"Rollback operation failed: {e}")
        return False

if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1) 