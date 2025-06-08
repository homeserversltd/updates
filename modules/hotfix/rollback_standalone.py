#!/usr/bin/env python3
"""
Standalone Emergency Rollback Script

This script can be used independently to perform emergency rollbacks
when the main hotfix system is compromised or unavailable.

Features:
- Emergency rollback from operation logs
- State snapshot restoration
- File backup restoration
- Service state restoration
- No dependencies on the main hotfix system
"""

import os
import sys
import json
import shutil
import subprocess
import time
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Optional

def log_message(message: str, level: str = "INFO") -> None:
    """Simple logging function."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {level}: {message}")

class EmergencyRollback:
    """Standalone emergency rollback system."""
    
    def __init__(self, backup_dir: str = "/var/backups/hotfix"):
        self.backup_dir = Path(backup_dir)
        self.snapshots_dir = self.backup_dir / "snapshots"
        
    def rollback_from_log(self, log_file: str) -> bool:
        """Perform emergency rollback from operation log file."""
        log_message("Starting emergency rollback from operation log")
        
        try:
            with open(log_file, 'r') as f:
                operations = json.load(f)
            
            if not isinstance(operations, list):
                log_message("Invalid log file format - expected list of operations", "ERROR")
                return False
            
            log_message(f"Found {len(operations)} operations to rollback")
            
            # Process operations in reverse order
            success_count = 0
            for operation in reversed(operations):
                if not operation.get("success", False):
                    log_message(f"Skipping failed operation: {operation.get('operation_id', 'unknown')}")
                    continue
                
                try:
                    if self._rollback_operation(operation):
                        success_count += 1
                except Exception as e:
                    log_message(f"Failed to rollback operation {operation.get('operation_id', 'unknown')}: {e}", "ERROR")
            
            log_message(f"Emergency rollback completed: {success_count}/{len(operations)} operations rolled back")
            return success_count > 0
            
        except Exception as e:
            log_message(f"Emergency rollback failed: {e}", "ERROR")
            return False
    
    def _rollback_operation(self, operation: Dict[str, Any]) -> bool:
        """Rollback a single operation."""
        operation_id = operation.get("operation_id", "unknown")
        operation_type = operation.get("type", "unknown")
        
        log_message(f"Rolling back operation: {operation_id} ({operation_type})")
        
        if operation_type == "copy":
            return self._rollback_copy_operation(operation)
        elif operation_type == "symlink":
            return self._rollback_symlink_operation(operation)
        elif operation_type == "append":
            return self._rollback_append_operation(operation)
        elif operation_type == "execute":
            return self._rollback_execute_operation(operation)
        else:
            log_message(f"Unknown operation type: {operation_type}", "WARNING")
            return False
    
    def _rollback_copy_operation(self, operation: Dict[str, Any]) -> bool:
        """Rollback a copy operation."""
        backup_path = operation.get("backup_path")
        target_path = operation.get("target")
        
        if not backup_path or not target_path:
            log_message("Missing backup_path or target for copy operation", "WARNING")
            return False
        
        backup_file = Path(backup_path)
        target_file = Path(target_path)
        
        if not backup_file.exists():
            log_message(f"Backup file not found: {backup_path}", "WARNING")
            return False
        
        try:
            # Remove current target
            if target_file.exists():
                if target_file.is_dir():
                    shutil.rmtree(target_file)
                else:
                    target_file.unlink()
            
            # Restore from backup
            target_file.parent.mkdir(parents=True, exist_ok=True)
            
            if backup_file.is_dir():
                shutil.copytree(backup_file, target_file)
            else:
                shutil.copy2(backup_file, target_file)
            
            log_message(f"Restored from backup: {backup_path} → {target_path}")
            return True
            
        except Exception as e:
            log_message(f"Failed to restore from backup: {e}", "ERROR")
            return False
    
    def _rollback_symlink_operation(self, operation: Dict[str, Any]) -> bool:
        """Rollback a symlink operation."""
        backup_path = operation.get("backup_path")
        target_path = operation.get("target")
        
        if not target_path:
            log_message("Missing target for symlink operation", "WARNING")
            return False
        
        target_file = Path(target_path)
        
        try:
            # Remove current symlink
            if target_file.exists() or target_file.is_symlink():
                target_file.unlink()
            
            # Restore from backup if it exists
            if backup_path:
                backup_file = Path(backup_path)
                if backup_file.exists():
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    
                    if backup_file.is_dir():
                        shutil.copytree(backup_file, target_file)
                    else:
                        shutil.copy2(backup_file, target_file)
                    
                    log_message(f"Restored symlink target from backup: {backup_path} → {target_path}")
                else:
                    log_message(f"Removed symlink: {target_path}")
            else:
                log_message(f"Removed symlink: {target_path}")
            
            return True
            
        except Exception as e:
            log_message(f"Failed to rollback symlink: {e}", "ERROR")
            return False
    
    def _rollback_append_operation(self, operation: Dict[str, Any]) -> bool:
        """Rollback an append operation."""
        target_path = operation.get("target")
        identifier = operation.get("identifier", operation.get("operation_id", "unknown"))
        marker = operation.get("marker", f"# HOTFIX {identifier.upper()}")
        
        if not target_path:
            log_message("Missing target for append operation", "WARNING")
            return False
        
        target_file = Path(target_path)
        
        if not target_file.exists():
            log_message(f"Target file not found: {target_path}", "WARNING")
            return False
        
        try:
            with open(target_file, 'r') as f:
                content = f.read()
            
            # Remove content between markers
            start_marker = f"{marker} START"
            end_marker = f"{marker} END"
            
            original_content = content
            while start_marker in content and end_marker in content:
                start_idx = content.find(start_marker)
                end_idx = content.find(end_marker) + len(end_marker)
                
                # Find the newline before start_marker to remove the entire line
                line_start = content.rfind('\n', 0, start_idx)
                if line_start == -1:
                    line_start = 0
                else:
                    line_start += 1  # Keep the newline
                
                # Find the newline after end_marker
                line_end = content.find('\n', end_idx)
                if line_end == -1:
                    line_end = len(content)
                else:
                    line_end += 1  # Include the newline
                
                content = content[:line_start] + content[line_end:]
            
            if content != original_content:
                with open(target_file, 'w') as f:
                    f.write(content)
                
                log_message(f"Removed appended content from: {target_path}")
                return True
            else:
                log_message(f"No appended content found to remove in: {target_path}", "WARNING")
                return False
            
        except Exception as e:
            log_message(f"Failed to rollback append operation: {e}", "ERROR")
            return False
    
    def _rollback_execute_operation(self, operation: Dict[str, Any]) -> bool:
        """Rollback an execute operation (limited capability)."""
        operation_id = operation.get("operation_id", "unknown")
        
        # Execute operations are generally not reversible automatically
        # We can only log that they occurred and suggest manual intervention
        log_message(f"Execute operation {operation_id} cannot be automatically rolled back", "WARNING")
        log_message("Manual intervention may be required to undo script effects", "WARNING")
        
        return False
    
    def list_snapshots(self) -> List[Dict[str, Any]]:
        """List available snapshots."""
        snapshots_index = self.snapshots_dir / "index.json"
        
        if not snapshots_index.exists():
            return []
        
        try:
            with open(snapshots_index, 'r') as f:
                data = json.load(f)
            
            snapshots = []
            for snapshot_id, snapshot_data in data.items():
                snapshots.append({
                    "id": snapshot_id,
                    "description": snapshot_data.get("description", ""),
                    "type": snapshot_data.get("snapshot_type", "unknown"),
                    "timestamp": snapshot_data.get("timestamp", 0),
                    "path": snapshot_data.get("data_path", "")
                })
            
            # Sort by timestamp (newest first)
            snapshots.sort(key=lambda s: s["timestamp"], reverse=True)
            return snapshots
            
        except Exception as e:
            log_message(f"Failed to load snapshots: {e}", "ERROR")
            return []
    
    def restore_snapshot(self, snapshot_id: str) -> bool:
        """Restore a specific snapshot."""
        snapshots_index = self.snapshots_dir / "index.json"
        
        if not snapshots_index.exists():
            log_message("No snapshots index found", "ERROR")
            return False
        
        try:
            with open(snapshots_index, 'r') as f:
                data = json.load(f)
            
            if snapshot_id not in data:
                log_message(f"Snapshot not found: {snapshot_id}", "ERROR")
                return False
            
            snapshot = data[snapshot_id]
            snapshot_type = snapshot.get("snapshot_type", "unknown")
            
            if snapshot_type == "file":
                return self._restore_file_snapshot(snapshot)
            elif snapshot_type == "service":
                return self._restore_service_snapshot(snapshot)
            elif snapshot_type == "database":
                log_message("Database snapshot restoration requires manual intervention", "WARNING")
                log_message(f"Database dump location: {snapshot.get('data_path', 'unknown')}", "INFO")
                return False
            elif snapshot_type == "system":
                log_message("System snapshot restoration requires manual intervention", "WARNING")
                log_message(f"System snapshot location: {snapshot.get('data_path', 'unknown')}", "INFO")
                return False
            else:
                log_message(f"Unknown snapshot type: {snapshot_type}", "ERROR")
                return False
            
        except Exception as e:
            log_message(f"Failed to restore snapshot: {e}", "ERROR")
            return False
    
    def _restore_file_snapshot(self, snapshot: Dict[str, Any]) -> bool:
        """Restore a file snapshot."""
        source_path = Path(snapshot["data_path"])
        target_path = Path(snapshot["metadata"]["original_path"])
        is_directory = snapshot["metadata"].get("is_directory", False)
        
        if not source_path.exists():
            log_message(f"Snapshot data not found: {source_path}", "ERROR")
            return False
        
        try:
            # Remove existing target
            if target_path.exists():
                if target_path.is_dir():
                    shutil.rmtree(target_path)
                else:
                    target_path.unlink()
            
            # Restore from snapshot
            target_path.parent.mkdir(parents=True, exist_ok=True)
            
            if is_directory:
                shutil.copytree(source_path, target_path)
            else:
                shutil.copy2(source_path, target_path)
            
            log_message(f"Restored file snapshot: {target_path}")
            return True
            
        except Exception as e:
            log_message(f"Failed to restore file snapshot: {e}", "ERROR")
            return False
    
    def _restore_service_snapshot(self, snapshot: Dict[str, Any]) -> bool:
        """Restore a service snapshot."""
        snapshot_path = Path(snapshot["data_path"])
        
        if not snapshot_path.exists():
            log_message(f"Service snapshot not found: {snapshot_path}", "ERROR")
            return False
        
        try:
            with open(snapshot_path, 'r') as f:
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
            
            log_message(f"Restored {success_count}/{len(service_states)} services")
            return success_count > 0
            
        except Exception as e:
            log_message(f"Failed to restore service snapshot: {e}", "ERROR")
            return False

def main():
    """Main entry point for standalone rollback script."""
    if len(sys.argv) < 2:
        print("Emergency Rollback Script")
        print("Usage:")
        print("  python rollback_standalone.py --list-snapshots")
        print("  python rollback_standalone.py --restore-snapshot <snapshot_id>")
        print("  python rollback_standalone.py --rollback-log <log_file.json>")
        print("  python rollback_standalone.py --help")
        return 1
    
    command = sys.argv[1]
    rollback = EmergencyRollback()
    
    try:
        if command == "--help":
            print("Emergency Rollback Script")
            print()
            print("Commands:")
            print("  --list-snapshots          List all available snapshots")
            print("  --restore-snapshot ID     Restore a specific snapshot")
            print("  --rollback-log FILE       Rollback operations from log file")
            print()
            print("Examples:")
            print("  python rollback_standalone.py --list-snapshots")
            print("  python rollback_standalone.py --restore-snapshot abc123def456")
            print("  python rollback_standalone.py --rollback-log /var/log/hotfix_operations.json")
            return 0
        
        elif command == "--list-snapshots":
            snapshots = rollback.list_snapshots()
            
            if not snapshots:
                print("No snapshots found")
                return 0
            
            print(f"Found {len(snapshots)} snapshots:")
            print()
            
            for snapshot in snapshots:
                print(f"ID: {snapshot['id']}")
                print(f"  Description: {snapshot['description']}")
                print(f"  Type: {snapshot['type']}")
                print(f"  Created: {time.ctime(snapshot['timestamp'])}")
                print(f"  Path: {snapshot['path']}")
                print()
            
            return 0
        
        elif command == "--restore-snapshot":
            if len(sys.argv) < 3:
                print("Error: --restore-snapshot requires a snapshot ID")
                return 1
            
            snapshot_id = sys.argv[2]
            success = rollback.restore_snapshot(snapshot_id)
            
            if success:
                print(f"Successfully restored snapshot: {snapshot_id}")
                return 0
            else:
                print(f"Failed to restore snapshot: {snapshot_id}")
                return 1
        
        elif command == "--rollback-log":
            if len(sys.argv) < 3:
                print("Error: --rollback-log requires a log file path")
                return 1
            
            log_file = sys.argv[2]
            
            if not os.path.exists(log_file):
                print(f"Error: Log file not found: {log_file}")
                return 1
            
            success = rollback.rollback_from_log(log_file)
            
            if success:
                print("Emergency rollback completed successfully")
                return 0
            else:
                print("Emergency rollback completed with errors")
                return 1
        
        else:
            print(f"Unknown command: {command}")
            print("Use --help for usage information")
            return 1
    
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        return 1
    except Exception as e:
        print(f"Error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 