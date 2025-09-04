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
import subprocess
import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from updates.index import log_message
from updates.utils.state_manager import StateManager

class HotfixOperationError(Exception):
    """Custom exception for hotfix operation failures."""
    pass

class HotfixManager:
    """Universal hotfix manager with flexible version checking and script execution."""
    
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
    
    def _check_version_condition(self, version_check: Dict[str, Any]) -> bool:
        """Check if a version condition is met."""
        check_type = version_check.get("type")
        
        if check_type == "always":
            return version_check.get("value", True)
        
        elif check_type == "file_exists":
            path = version_check.get("path")
            invert = version_check.get("invert", False)
            exists = Path(path).exists() if path else False
            return not exists if invert else exists
        
        elif check_type == "module_schema":
            module = version_check.get("module")
            max_version = version_check.get("max_version")
            
            if not module or not max_version:
                return False
            
            # Try to get module schema version
            try:
                module_path = f"/var/www/homeserver/src/tablets/{module}/index.json"
                if not Path(module_path).exists():
                    return True  # Module doesn't exist, apply hotfix
                
                with open(module_path, 'r') as f:
                    module_config = json.load(f)
                
                current_version = module_config.get("metadata", {}).get("schema_version", "0.0.0")
                
                # Simple version comparison
                from packaging import version
                return version.parse(current_version) <= version.parse(max_version)
                
            except Exception as e:
                log_message(f"Error checking module schema version: {e}", "ERROR")
                return False
        
        elif check_type == "binary_version":
            binary = version_check.get("binary")
            max_version = version_check.get("max_version")
            version_flag = version_check.get("version_flag", "--version")
            
            if not binary or not max_version:
                return False
            
            try:
                # Run the binary with version flag
                result = subprocess.run(
                    [binary, version_flag],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if result.returncode != 0:
                    return True  # Binary not found or failed, apply hotfix
                
                # Extract version from output (first line, first word after last space)
                output_lines = result.stdout.strip().split('\n')
                if not output_lines:
                    return True
                
                version_text = output_lines[0].strip()
                # Try to extract version number
                import re
                version_match = re.search(r'(\d+\.\d+\.\d+)', version_text)
                if not version_match:
                    return True  # Can't parse version, apply hotfix
                
                current_version = version_match.group(1)
                
                from packaging import version
                return version.parse(current_version) <= version.parse(max_version)
                
            except Exception as e:
                log_message(f"Error checking binary version: {e}", "ERROR")
                return True  # Error occurred, apply hotfix
        
        else:
            log_message(f"Unknown version check type: {check_type}", "ERROR")
            return False
    
    def _should_apply_target(self, target: Dict[str, Any]) -> bool:
        """Check if a target should be applied based on version check and has_run status."""
        # Check if already run
        if target.get('has_run', False):
            log_message(f"Target {target.get('id', 'unknown')} has already run, skipping")
            return False
        
        # Check version condition
        version_check = target.get('version_check', {})
        if not version_check:
            return True  # No version check, apply always
        
        should_apply = self._check_version_condition(version_check)
        log_message(f"Version check for {target.get('id', 'unknown')}: {should_apply}")
        return should_apply
    
    def _execute_hotfix_script(self, target: Dict[str, Any]) -> bool:
        """Execute the hotfix script for a target."""
        target_id = target.get('id', 'unknown')
        script_name = f"{target_id}.sh"
        script_path = self.src_dir / script_name
        
        if not script_path.exists():
            log_message(f"Hotfix script not found: {script_path}", "ERROR")
            return False
        
        log_message(f"Executing hotfix script: {script_name}")
        
        try:
            # Make script executable
            os.chmod(script_path, 0o755)
            
            # Execute the script
            result = subprocess.run(
                [str(script_path)],
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode == 0:
                log_message(f"Hotfix script {script_name} completed successfully")
                if result.stdout:
                    log_message(f"Script output: {result.stdout}")
                return True
            else:
                log_message(f"Hotfix script {script_name} failed with return code {result.returncode}", "ERROR")
                if result.stderr:
                    log_message(f"Script error: {result.stderr}", "ERROR")
                return False
                
        except subprocess.TimeoutExpired:
            log_message(f"Hotfix script {script_name} timed out", "ERROR")
            return False
        except Exception as e:
            log_message(f"Error executing hotfix script {script_name}: {e}", "ERROR")
            return False
    
    def _mark_target_as_run(self, target_id: str) -> bool:
        """Mark a target as having run successfully by updating the index.json file."""
        try:
            # Update the config in memory
            for target in self.config.get('targets', []):
                if target.get('id') == target_id:
                    target['has_run'] = True
                    break
            
            # Write the updated config back to disk
            with open(self.index_file, 'w') as f:
                json.dump(self.config, f, indent=4)
            
            log_message(f"Marked target {target_id} as completed")
            return True
            
        except Exception as e:
            log_message(f"Failed to mark target {target_id} as completed: {e}", "ERROR")
            return False
    
    def _process_target(self, target: Dict[str, Any]) -> bool:
        """Process a single target with version check and script execution."""
        target_id = target["id"]
        description = target.get("description", target_id)
        
        log_message(f"Processing target: {target_id} - {description}")
        
        # Check if this target should be applied
        if not self._should_apply_target(target):
            log_message(f"Target {target_id} skipped - version check failed or already run")
            return True  # Don't count as failure, just skip
        
        # Execute the hotfix script
        script_success = self._execute_hotfix_script(target)
        if not script_success:
            log_message(f"Hotfix script failed for target {target_id}", "ERROR")
            return False
        
        # Mark target as run after successful completion
        self._mark_target_as_run(target_id)
        
        log_message(f"Target {target_id} completed successfully")
        return True
    
    def apply_hotfixes(self) -> Dict[str, Any]:
        """Apply all hotfix targets."""
        log_message("Starting hotfix application...")
        
        try:
            targets = self.config.get("targets", [])
            
            if not targets:
                log_message("No targets found in configuration")
                return {"success": True, "targets": [], "message": "No targets to apply"}
            
            log_message(f"Found {len(targets)} targets to process")
            
            # Process each target
            target_results = []
            successful_targets = 0
            
            for target in targets:
                target_id = target.get("id", "unknown")
                
                try:
                    target_success = self._process_target(target)
                    
                    target_result = {
                        "target_id": target_id,
                        "description": target.get("description", ""),
                        "success": target_success,
                        "target_type": target.get("target_id", "unknown")
                    }
                    
                    if target_success:
                        successful_targets += 1
                        log_message(f"Target {target_id} succeeded")
                    else:
                        log_message(f"Target {target_id} failed but continuing with other targets", "WARNING")
                        target_result["error"] = "Target processing failed"
                    
                    target_results.append(target_result)
                    
                except Exception as e:
                    log_message(f"Unexpected error in target {target_id}: {e}", "ERROR")
                    target_results.append({
                        "target_id": target_id,
                        "description": target.get("description", ""),
                        "success": False,
                        "error": str(e),
                        "target_type": target.get("target_id", "unknown")
                    })
            
            # Determine overall success
            overall_success = successful_targets > 0
            
            result = {
                "success": overall_success,
                "targets_processed": len(targets),
                "targets_successful": successful_targets,
                "targets_failed": len(targets) - successful_targets,
                "target_results": target_results
            }
            
            if overall_success:
                result["message"] = f"Hotfix completed: {successful_targets}/{len(targets)} targets successful"
                log_message(result["message"])
            else:
                result["message"] = "All targets failed"
                result["error"] = "No targets completed successfully"
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
        args: List of arguments (supports '--check', '--version')
        
    Returns:
        dict: Status and results of the hotfix operation
    """
    if args is None:
        args = []
    
    # Get module path
    module_path = os.path.dirname(os.path.abspath(__file__))
    
    try:
        manager = HotfixManager(module_path)
        
        if "--check" in args:
            config = manager.config
            targets = config.get("targets", [])
            
            log_message(f"Hotfix module status: {len(targets)} targets configured")
            return {
                "success": True,
                "total_targets": len(targets),
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