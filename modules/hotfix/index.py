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

import os
import shutil
import subprocess
import json
import time
from pathlib import Path
from typing import Dict, List, Any, Optional
from updates.index import log_message
from updates.utils.state_manager import StateManager
from updates.utils.permissions import PermissionManager

class HotfixOperationError(Exception):
    """Custom exception for hotfix operation failures."""
    pass

def restore_hotfix_permissions(config: Dict[str, Any]) -> bool:
    """
    Restore permissions for all hotfix operations that have permission specifications.
    
    Args:
        config: Module configuration containing pools and operations
        
    Returns:
        bool: True if permissions restored successfully, False otherwise
    """
    try:
        log_message("Restoring hotfix permissions...")
        
        # Initialize PermissionManager
        permission_manager = PermissionManager()
        
        # Get all pools
        pools = config.get('pools', [])
        if not pools:
            log_message("No pools found, skipping permission restoration")
            return True
        
        # Build targets from operations with permission specifications
        targets = []
        
        for pool in pools:
            pool_id = pool.get('id', 'unknown')
            operations = pool.get('operations', [])
            
            for operation in operations:
                destination = operation.get('destination')
                permissions = operation.get('permissions')
                
                if destination and permissions:
                    owner = permissions.get('owner', 'root')
                    group = permissions.get('group', 'root')
                    mode = permissions.get('mode', '644')
                    
                    target = permission_manager.create_target(
                        path=destination,
                        owner=owner,
                        group=group,
                        mode=mode,
                        recursive=False  # Hotfix operations are typically single files
                    )
                    targets.append(target)
                    log_message(f"Added permission target: {destination} ({owner}:{group} {mode})")
        
        if not targets:
            log_message("No permission targets found in hotfix operations")
            return True
        
        # Apply permissions
        success = permission_manager.apply_permissions(targets)
        
        if success:
            log_message(f"Successfully restored permissions for {len(targets)} hotfix targets")
            return True
        else:
            log_message("Failed to restore hotfix permissions", "ERROR")
            return False
            
    except Exception as e:
        log_message(f"Error restoring hotfix permissions: {e}", "ERROR")
        return False

class HotfixManager:
    """Pool-based hotfix manager with StateManager integration."""
    
    def __init__(self, module_path: str):
        self.module_path = Path(module_path)
        self.index_file = self.module_path / "index.json"
        self.config = self._load_config()
        self.state_manager = StateManager("/var/backups/hotfix")
        self.src_dir = self.module_path / "src"
        
    def _load_config(self) -> Dict[str, Any]:
        """Load the hotfix configuration from index.json."""
        try:
            with open(self.index_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            log_message(f"Failed to load hotfix config: {e}", "ERROR")
            return {}
    
    def _execute_commands(self, commands: List[str], description: str) -> bool:
        """Execute a list of commands and return success status."""
        if not commands:
            return True
        
        log_message(f"Executing {description} commands...")
        
        for command in commands:
            try:
                log_message(f"Running: {command}")
                result = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                
                if result.returncode != 0:
                    log_message(f"Command failed: {command}", "ERROR")
                    log_message(f"Error output: {result.stderr}", "ERROR")
                    return False
                
                if result.stdout:
                    log_message(f"Command output: {result.stdout}")
                
                log_message(f"Command succeeded: {command}")
                
            except subprocess.TimeoutExpired:
                log_message(f"Command timed out: {command}", "ERROR")
                return False
            except Exception as e:
                log_message(f"Command execution failed: {command} - {e}", "ERROR")
                return False
        
        log_message(f"All {description} commands completed successfully")
        return True
    
    def _apply_operation_permissions(self, operation: Dict[str, Any]) -> bool:
        """Apply permissions for a single operation if specified."""
        permissions = operation.get('permissions')
        if not permissions:
            return True  # No permissions specified, that's fine
        
        destination = operation.get('destination')
        if not destination:
            return True
        
        try:
            # Initialize PermissionManager
            permission_manager = PermissionManager()
            
            # Create target from operation permissions
            owner = permissions.get('owner', 'root')
            group = permissions.get('group', 'root')
            mode = permissions.get('mode', '644')
            
            target = permission_manager.create_target(
                path=destination,
                owner=owner,
                group=group,
                mode=mode,
                recursive=False
            )
            
            # Apply permissions
            success = permission_manager.apply_permissions([target])
            
            if success:
                log_message(f"Applied permissions to {destination}: {owner}:{group} {mode}")
                return True
            else:
                log_message(f"Failed to apply permissions to {destination}", "ERROR")
                return False
                
        except Exception as e:
            log_message(f"Error applying permissions to {destination}: {e}", "ERROR")
            return False
    
    def _apply_pool_operations(self, pool: Dict[str, Any]) -> bool:
        """Apply all file operations in a pool."""
        pool_id = pool["id"]
        operations = pool.get("operations", [])
        
        if not operations:
            log_message(f"No operations in pool {pool_id}")
            return True
        
        log_message(f"Applying {len(operations)} operations in pool {pool_id}")
        
        for operation in operations:
            try:
                target_file = operation["target"]
                destination = operation["destination"]
                
                # Construct source path
                source_path = self.src_dir / target_file
                destination_path = Path(destination)
                
                if not source_path.exists():
                    log_message(f"Source file not found: {source_path}", "ERROR")
                    return False
                
                # Ensure destination directory exists
                destination_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Copy file
                shutil.copy2(source_path, destination_path)
                log_message(f"Copied: {source_path} → {destination_path}")
                
                # Apply permissions if specified
                if not self._apply_operation_permissions(operation):
                    log_message(f"Failed to apply permissions for operation in pool {pool_id}", "ERROR")
                    return False
                
            except Exception as e:
                log_message(f"Failed to apply operation in pool {pool_id}: {e}", "ERROR")
                return False
        
        log_message(f"All operations in pool {pool_id} applied successfully")
        return True
    
    def _process_pool(self, pool: Dict[str, Any]) -> bool:
        """Process a single pool with backup, apply, closure, and rollback logic."""
        pool_id = pool["id"]
        description = pool.get("description", pool_id)
        operations = pool.get("operations", [])
        closure_commands = pool.get("closure", [])
        
        log_message(f"Processing pool: {pool_id} - {description}")
        
        if not operations:
            log_message(f"Pool {pool_id} has no operations, skipping")
            return True
        
        # Collect all destination files for backup
        destination_files = []
        for operation in operations:
            destination_files.append(operation["destination"])
        
        try:
            # Backup phase - backup all destination files
            log_message(f"Backing up {len(destination_files)} files for pool {pool_id}")
            backup_success = self.state_manager.backup_module_state(
                module_name=f"hotfix_pool_{pool_id}",
                description=f"Pool {pool_id} backup: {description}",
                files=destination_files
            )
            
            if not backup_success:
                log_message(f"Failed to create backup for pool {pool_id}", "ERROR")
                return False
            
            # Apply phase - copy all source files to destinations with permissions
            apply_success = self._apply_pool_operations(pool)
            if not apply_success:
                log_message(f"Failed to apply operations for pool {pool_id}, rolling back", "ERROR")
                self._rollback_pool(pool_id)
                return False
            
            # Closure phase - execute closure commands
            closure_success = self._execute_commands(closure_commands, f"pool {pool_id} closure")
            if not closure_success:
                log_message(f"Closure commands failed for pool {pool_id}, rolling back", "ERROR")
                self._rollback_pool(pool_id)
                return False
            
            log_message(f"Pool {pool_id} completed successfully")
            return True
            
        except Exception as e:
            log_message(f"Unexpected error processing pool {pool_id}: {e}", "ERROR")
            self._rollback_pool(pool_id)
            return False
    
    def _rollback_pool(self, pool_id: str) -> None:
        """Rollback a pool using StateManager."""
        log_message(f"Rolling back pool: {pool_id}")
        
        try:
            restore_success = self.state_manager.restore_module_state(f"hotfix_pool_{pool_id}")
            if restore_success:
                log_message(f"Successfully rolled back pool {pool_id}")
                
                # Restore permissions after rollback if needed
                log_message(f"Restoring permissions after rollback for pool {pool_id}")
                restore_hotfix_permissions(self.config)
                
            else:
                log_message(f"Failed to rollback pool {pool_id}", "ERROR")
        except Exception as e:
            log_message(f"Error during rollback of pool {pool_id}: {e}", "ERROR")
    
    def apply_hotfixes(self) -> Dict[str, Any]:
        """Apply all hotfix pools."""
        log_message("Starting hotfix application...")
        
        try:
            pools = self.config.get("pools", [])
            final_closure = self.config.get("finalClosure", [])
            
            if not pools:
                log_message("No pools found in configuration")
                return {"success": True, "pools": [], "message": "No pools to apply"}
            
            log_message(f"Found {len(pools)} pools to process")
            
            # Process each pool
            pool_results = []
            successful_pools = 0
            
            for pool in pools:
                pool_id = pool.get("id", "unknown")
                
                try:
                    pool_success = self._process_pool(pool)
                    
                    pool_result = {
                        "pool_id": pool_id,
                        "description": pool.get("description", ""),
                        "success": pool_success,
                        "operations_count": len(pool.get("operations", []))
                    }
                    
                    if pool_success:
                        successful_pools += 1
                        log_message(f"Pool {pool_id} succeeded")
                    else:
                        log_message(f"Pool {pool_id} failed but continuing with other pools", "WARNING")
                        pool_result["error"] = "Pool processing failed"
                    
                    pool_results.append(pool_result)
                    
                except Exception as e:
                    log_message(f"Unexpected error in pool {pool_id}: {e}", "ERROR")
                    pool_results.append({
                        "pool_id": pool_id,
                        "description": pool.get("description", ""),
                        "success": False,
                        "error": str(e),
                        "operations_count": len(pool.get("operations", []))
                    })
            
            # Execute final closure commands if any pools succeeded
            final_closure_success = True
            if successful_pools > 0 and final_closure:
                log_message("Executing final closure commands...")
                final_closure_success = self._execute_commands(final_closure, "final closure")
                
                if not final_closure_success:
                    log_message("Final closure commands failed, but not rolling back pools", "WARNING")
            
            # Determine overall success
            overall_success = successful_pools > 0
            
            result = {
                "success": overall_success,
                "pools_processed": len(pools),
                "pools_successful": successful_pools,
                "pools_failed": len(pools) - successful_pools,
                "final_closure_success": final_closure_success,
                "pool_results": pool_results
            }
            
            if overall_success:
                result["message"] = f"Hotfix completed: {successful_pools}/{len(pools)} pools successful"
                log_message(result["message"])
            else:
                result["message"] = "All pools failed"
                result["error"] = "No pools completed successfully"
                log_message(result["message"], "ERROR")
            
            return result
            
        except Exception as e:
            log_message(f"Hotfix application failed: {e}", "ERROR")
            return {
                "success": False,
                "error": str(e),
                "message": "Hotfix application encountered an unexpected error"
            }

def main(args=None):
    """
    Main entry point for hotfix module.
    
    Args:
        args: List of arguments (supports '--check', '--version', '--fix-permissions')
        
    Returns:
        dict: Status and results of the hotfix operation
    """
    if args is None:
        args = []
    
    # Get module path
    module_path = os.path.dirname(os.path.abspath(__file__))
    
    try:
        manager = HotfixManager(module_path)
        
        if "--fix-permissions" in args:
            log_message("Fixing hotfix permissions...")
            success = restore_hotfix_permissions(manager.config)
            return {
                "success": success,
                "message": "Hotfix permissions fixed" if success else "Failed to fix hotfix permissions"
            }
        
        elif "--check" in args:
            config = manager.config
            pools = config.get("pools", [])
            
            total_operations = sum(len(pool.get("operations", [])) for pool in pools)
            
            log_message(f"Hotfix module status: {len(pools)} pools with {total_operations} total operations")
            return {
                "success": True,
                "total_pools": len(pools),
                "total_operations": total_operations,
                "schema_version": config.get("metadata", {}).get("schema_version", "unknown")
            }
        
        elif "--version" in args:
            config = manager.config
            schema_version = config.get("metadata", {}).get("schema_version", "unknown")
            log_message(f"Hotfix module version: {schema_version}")
            return {
                "success": True,
                "schema_version": schema_version,
                "module": "hotfix"
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