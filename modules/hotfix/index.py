import os
import shutil
import subprocess
import json
import time
from pathlib import Path
from typing import Dict, List, Any, Optional
from initialization.files.user_local_lib.updates import log_message

class HotfixOperationError(Exception):
    """Custom exception for hotfix operation failures."""
    pass

class HotfixManager:
    """Manages hotfix operations with backup and rollback capabilities."""
    
    def __init__(self, module_path: str):
        self.module_path = Path(module_path)
        self.index_file = self.module_path / "index.json"
        self.config = self._load_config()
        self.backup_dir = Path(self.config.get("config", {}).get("backup_dir", "/var/backups/hotfix"))
        self.operations_log = []
        
    def _load_config(self) -> Dict[str, Any]:
        """Load the hotfix configuration from index.json."""
        try:
            with open(self.index_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            log_message(f"Failed to load hotfix config: {e}", "ERROR")
            return {}
    
    def _create_backup_dir(self) -> None:
        """Ensure backup directory exists."""
        try:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            log_message(f"Backup directory ready: {self.backup_dir}")
        except Exception as e:
            raise HotfixOperationError(f"Failed to create backup directory: {e}")
    
    def _create_backup(self, target_path: str, operation_id: str) -> Optional[str]:
        """Create a backup of the target file/directory."""
        target = Path(target_path)
        if not target.exists():
            log_message(f"Target does not exist, no backup needed: {target_path}")
            return None
        
        try:
            timestamp = int(time.time())
            backup_name = f"{operation_id}_{target.name}_{timestamp}"
            backup_path = self.backup_dir / backup_name
            
            if target.is_dir():
                shutil.copytree(target, backup_path)
            else:
                shutil.copy2(target, backup_path)
            
            log_message(f"Created backup: {target_path} → {backup_path}")
            return str(backup_path)
            
        except Exception as e:
            raise HotfixOperationError(f"Failed to create backup for {target_path}: {e}")
    
    def _set_permissions(self, path: str, permissions: Dict[str, str]) -> None:
        """Set file permissions and ownership."""
        try:
            if "mode" in permissions:
                os.chmod(path, int(permissions["mode"], 8))
                log_message(f"Set permissions {permissions['mode']} on {path}")
            
            if "user" in permissions or "group" in permissions:
                user = permissions.get("user", "")
                group = permissions.get("group", "")
                if user or group:
                    cmd = ["chown"]
                    if user and group:
                        cmd.append(f"{user}:{group}")
                    elif user:
                        cmd.append(user)
                    elif group:
                        cmd.append(f":{group}")
                    cmd.append(path)
                    
                    subprocess.run(cmd, check=True, capture_output=True)
                    log_message(f"Set ownership {user}:{group} on {path}")
                    
        except Exception as e:
            log_message(f"Failed to set permissions on {path}: {e}", "WARNING")
    
    def _perform_copy_operation(self, operation: Dict[str, Any]) -> Dict[str, Any]:
        """Perform a copy operation."""
        source_path = self.module_path / operation["source"]
        target_path = Path(operation["target"])
        
        if not source_path.exists():
            raise HotfixOperationError(f"Source file not found: {source_path}")
        
        # Create backup if requested
        backup_path = None
        if operation.get("backup", False):
            backup_path = self._create_backup(str(target_path), operation["id"])
        
        # Ensure target directory exists
        target_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Copy file
        shutil.copy2(source_path, target_path)
        log_message(f"Copied: {source_path} → {target_path}")
        
        # Set permissions
        if "permissions" in operation:
            self._set_permissions(str(target_path), operation["permissions"])
        
        return {
            "operation_id": operation["id"],
            "type": "copy",
            "source": str(source_path),
            "target": str(target_path),
            "backup_path": backup_path,
            "success": True
        }
    
    def _perform_append_operation(self, operation: Dict[str, Any]) -> Dict[str, Any]:
        """Perform an append operation."""
        source_path = self.module_path / operation["source"]
        target_path = Path(operation["target"])
        
        if not source_path.exists():
            raise HotfixOperationError(f"Source file not found: {source_path}")
        
        # Create backup if requested
        backup_path = None
        if operation.get("backup", False):
            backup_path = self._create_backup(str(target_path), operation["id"])
        
        # Read source content
        with open(source_path, 'r') as f:
            source_content = f.read()
        
        # Prepare append content with markers
        identifier = operation.get("identifier", operation["id"])
        marker = operation.get("marker", f"# HOTFIX {identifier.upper()}")
        
        append_content = f"\n{marker} START\n{source_content}\n{marker} END\n"
        
        # Append to target file
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, 'a') as f:
            f.write(append_content)
        
        log_message(f"Appended content from {source_path} to {target_path}")
        
        return {
            "operation_id": operation["id"],
            "type": "append",
            "source": str(source_path),
            "target": str(target_path),
            "identifier": identifier,
            "marker": marker,
            "backup_path": backup_path,
            "success": True
        }
    
    def _perform_symlink_operation(self, operation: Dict[str, Any]) -> Dict[str, Any]:
        """Perform a symlink operation."""
        source_path = self.module_path / operation["source"]
        target_path = Path(operation["target"])
        
        if not source_path.exists():
            raise HotfixOperationError(f"Source file not found: {source_path}")
        
        # Create backup if target exists and backup requested
        backup_path = None
        if operation.get("backup", False) and target_path.exists():
            backup_path = self._create_backup(str(target_path), operation["id"])
        
        # Remove existing target if it exists
        if target_path.exists() or target_path.is_symlink():
            target_path.unlink()
        
        # Ensure target directory exists
        target_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Create symlink
        target_path.symlink_to(source_path.absolute())
        log_message(f"Created symlink: {target_path} → {source_path}")
        
        # Set permissions on source if specified
        if "permissions" in operation:
            self._set_permissions(str(source_path), operation["permissions"])
        
        return {
            "operation_id": operation["id"],
            "type": "symlink",
            "source": str(source_path),
            "target": str(target_path),
            "backup_path": backup_path,
            "success": True
        }
    
    def _perform_execute_operation(self, operation: Dict[str, Any]) -> Dict[str, Any]:
        """Perform an execute operation."""
        source_path = self.module_path / operation["source"]
        
        if not source_path.exists():
            raise HotfixOperationError(f"Script not found: {source_path}")
        
        # Make script executable
        os.chmod(source_path, 0o755)
        
        # Prepare execution environment
        working_dir = operation.get("working_dir", str(self.module_path))
        timeout = operation.get("timeout", 300)
        
        # Execute script
        log_message(f"Executing script: {source_path}")
        result = subprocess.run(
            [str(source_path)],
            cwd=working_dir,
            timeout=timeout,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            raise HotfixOperationError(f"Script execution failed: {result.stderr}")
        
        log_message(f"Script executed successfully: {source_path}")
        if result.stdout:
            log_message(f"Script output: {result.stdout}")
        
        # Cleanup script if requested
        if operation.get("cleanup_after", False):
            source_path.unlink()
            log_message(f"Cleaned up script: {source_path}")
        
        return {
            "operation_id": operation["id"],
            "type": "execute",
            "source": str(source_path),
            "working_dir": working_dir,
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "success": True
        }
    
    def _run_validation_checks(self, checks: List[Dict[str, Any]], check_type: str) -> bool:
        """Run validation checks."""
        if not checks:
            return True
        
        log_message(f"Running {check_type} validation checks...")
        
        for check in checks:
            try:
                command = check["command"]
                expected = check.get("expected")
                expected_exit_code = check.get("expected_exit_code")
                description = check.get("description", command)
                
                log_message(f"Validation check: {description}")
                
                result = subprocess.run(
                    command.split(),
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                # Check exit code if specified
                if expected_exit_code is not None:
                    if result.returncode != expected_exit_code:
                        log_message(f"Validation failed: Expected exit code {expected_exit_code}, got {result.returncode}", "ERROR")
                        return False
                
                # Check output if specified
                if expected is not None:
                    if expected not in result.stdout:
                        log_message(f"Validation failed: Expected '{expected}' in output, got '{result.stdout}'", "ERROR")
                        return False
                
                log_message(f"Validation passed: {description}")
                
            except Exception as e:
                log_message(f"Validation check failed: {e}", "ERROR")
                return False
        
        log_message(f"All {check_type} validation checks passed")
        return True
    
    def apply_hotfixes(self) -> Dict[str, Any]:
        """Apply all enabled hotfix operations."""
        log_message("Starting hotfix application...")
        
        try:
            self._create_backup_dir()
            
            operations = self.config.get("operations", [])
            enabled_operations = [op for op in operations if op.get("enabled", False)]
            
            if not enabled_operations:
                log_message("No enabled operations found")
                return {"success": True, "operations": [], "message": "No operations to apply"}
            
            log_message(f"Found {len(enabled_operations)} enabled operations")
            
            # Run pre-checks
            validation_config = self.config.get("validation", {})
            if not self._run_validation_checks(validation_config.get("pre_checks", []), "pre"):
                raise HotfixOperationError("Pre-validation checks failed")
            
            # Apply operations
            results = []
            for operation in enabled_operations:
                try:
                    log_message(f"Applying operation: {operation['id']} ({operation['type']})")
                    
                    if operation["type"] == "copy":
                        result = self._perform_copy_operation(operation)
                    elif operation["type"] == "append":
                        result = self._perform_append_operation(operation)
                    elif operation["type"] == "symlink":
                        result = self._perform_symlink_operation(operation)
                    elif operation["type"] == "execute":
                        result = self._perform_execute_operation(operation)
                    else:
                        raise HotfixOperationError(f"Unknown operation type: {operation['type']}")
                    
                    results.append(result)
                    self.operations_log.append(result)
                    log_message(f"Operation {operation['id']} completed successfully")
                    
                except Exception as e:
                    error_result = {
                        "operation_id": operation["id"],
                        "type": operation["type"],
                        "success": False,
                        "error": str(e)
                    }
                    results.append(error_result)
                    self.operations_log.append(error_result)
                    
                    if self.config.get("config", {}).get("rollback_on_failure", True):
                        log_message(f"Operation {operation['id']} failed, initiating rollback", "ERROR")
                        self._rollback_operations()
                        raise HotfixOperationError(f"Hotfix failed at operation {operation['id']}: {e}")
                    else:
                        log_message(f"Operation {operation['id']} failed, continuing: {e}", "WARNING")
            
            # Run post-checks
            if not self._run_validation_checks(validation_config.get("post_checks", []), "post"):
                if self.config.get("config", {}).get("rollback_on_failure", True):
                    log_message("Post-validation failed, initiating rollback", "ERROR")
                    self._rollback_operations()
                    raise HotfixOperationError("Post-validation checks failed")
                else:
                    log_message("Post-validation failed, but rollback disabled", "WARNING")
            
            log_message("All hotfix operations completed successfully")
            return {
                "success": True,
                "operations": results,
                "message": f"Applied {len(results)} operations successfully"
            }
            
        except Exception as e:
            log_message(f"Hotfix application failed: {e}", "ERROR")
            return {
                "success": False,
                "error": str(e),
                "operations": self.operations_log
            }
    
    def _rollback_operations(self) -> None:
        """Rollback applied operations using backups."""
        log_message("Starting rollback of hotfix operations...")
        
        # Reverse order for rollback
        operations_to_rollback = list(reversed(self.operations_log))
        
        for operation in operations_to_rollback:
            if not operation.get("success", False):
                continue
                
            try:
                operation_id = operation["operation_id"]
                operation_type = operation["type"]
                
                log_message(f"Rolling back operation: {operation_id} ({operation_type})")
                
                if operation_type in ["copy", "symlink"] and operation.get("backup_path"):
                    # Restore from backup
                    backup_path = Path(operation["backup_path"])
                    target_path = Path(operation["target"])
                    
                    if backup_path.exists():
                        if target_path.exists():
                            target_path.unlink()
                        shutil.copy2(backup_path, target_path)
                        log_message(f"Restored from backup: {backup_path} → {target_path}")
                
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
                        
                        log_message(f"Removed appended content from {target_path}")
                
                log_message(f"Rollback completed for operation: {operation_id}")
                
            except Exception as e:
                log_message(f"Failed to rollback operation {operation.get('operation_id', 'unknown')}: {e}", "ERROR")
        
        log_message("Rollback completed")

def main(args=None):
    """
    Main entry point for hotfix module.
    
    Args:
        args: List of arguments (supports '--rollback', '--check')
        
    Returns:
        dict: Status and results of the hotfix operation
    """
    if args is None:
        args = []
    
    # Get module path
    module_path = os.path.dirname(os.path.abspath(__file__))
    
    try:
        manager = HotfixManager(module_path)
        
        if "--rollback" in args:
            log_message("Manual rollback requested")
            manager._rollback_operations()
            return {"success": True, "message": "Rollback completed"}
        
        elif "--check" in args:
            config = manager.config
            operations = config.get("operations", [])
            enabled_count = sum(1 for op in operations if op.get("enabled", False))
            
            log_message(f"Hotfix module status: {enabled_count} operations enabled out of {len(operations)} total")
            return {
                "success": True,
                "total_operations": len(operations),
                "enabled_operations": enabled_count,
                "schema_version": config.get("metadata", {}).get("schema_version", "unknown")
            }
        
        else:
            # Apply hotfixes
            return manager.apply_hotfixes()
            
    except Exception as e:
        log_message(f"Hotfix module failed: {e}", "ERROR")
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    import sys
    result = main(sys.argv[1:])
    if not result.get("success", False):
        sys.exit(1)
