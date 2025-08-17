"""
HOMESERVER Website Maintenance Module

This module provides maintenance tasks for the website that run automatically during updates.
Maintenance tasks include keeping dependencies current and validating system health.
Maintenance is ALWAYS executed as part of the update process.
"""

import os
import subprocess
from typing import Dict, Any
from datetime import datetime
from updates.utils import log_message
import json


class WebsiteMaintenance:
    """Maintenance tasks for the website module."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.base_dir = config.get('config', {}).get('target_paths', {}).get('base_directory', '/var/www/homeserver')
    
    def run_maintenance(self) -> Dict[str, Any]:
        """Run all maintenance tasks for this module."""
        results = {
            "module": "website",
            "success": True,
            "tasks": {},
            "timestamp": datetime.now().isoformat(),
            "errors": []
        }
        
        try:
            # Task 1: Update Browserslist database
            log_message("Running Browserslist database update...")
            browserslist_result = self._update_browserslist()
            results["tasks"]["browserslist"] = browserslist_result
            
            # Task 2: Clean build artifacts
            log_message("Cleaning build artifacts...")
            cleanup_result = self._cleanup_build_artifacts()
            results["tasks"]["cleanup"] = cleanup_result
            
            # Task 3: Validate file permissions
            log_message("Validating file permissions...")
            permissions_result = self._validate_permissions()
            results["tasks"]["permissions"] = permissions_result
            
            # Task 4: Check npm package health
            log_message("Checking npm package health...")
            npm_health_result = self._check_npm_health()
            results["tasks"]["npm_health"] = npm_health_result
            
        except Exception as e:
            log_message(f"Maintenance failed: {e}", "ERROR")
            results["success"] = False
            results["errors"].append(str(e))
        
        return results
    
    def _update_browserslist(self) -> Dict[str, Any]:
        """Update Browserslist database using npx."""
        try:
            if not os.path.exists(self.base_dir):
                return {
                    "success": False,
                    "error": f"Base directory not found: {self.base_dir}"
                }
            
            # Use --yes to avoid interactive prompts
            result = subprocess.run(
                ["npx", "--yes", "update-browserslist-db@latest"],
                cwd=self.base_dir,
                capture_output=True,
                text=True,
                timeout=180,
            )
            
            if result.returncode != 0:
                return {
                    "success": False,
                    "error": f"Browserslist update failed: {result.stderr}",
                    "returncode": result.returncode
                }
            
            # Log a summary of the output
            output_lines = result.stdout.strip().split('\n') if result.stdout else []
            return {
                "success": True,
                "output_lines": len(output_lines),
                "last_lines": output_lines[-5:] if output_lines else []
            }
            
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "Browserslist update timed out"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def _cleanup_build_artifacts(self) -> Dict[str, Any]:
        """Clean up build artifacts and temporary files."""
        try:
            cleanup_paths = [
                os.path.join(self.base_dir, 'node_modules/.cache'),
                os.path.join(self.base_dir, '.npm'),
                os.path.join(self.base_dir, 'npm-debug.log'),
                os.path.join(self.base_dir, 'yarn-error.log')
            ]
            
            cleaned_count = 0
            failed_count = 0
            
            for path in cleanup_paths:
                try:
                    if os.path.exists(path):
                        if os.path.isdir(path):
                            import shutil
                            shutil.rmtree(path)
                        else:
                            os.remove(path)
                        cleaned_count += 1
                except Exception as e:
                    failed_count += 1
                    log_message(f"Failed to clean {path}: {e}", "WARNING")
            
            return {
                "success": True,
                "cleaned_count": cleaned_count,
                "failed_count": failed_count,
                "total_paths": len(cleanup_paths)
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def _validate_permissions(self) -> Dict[str, Any]:
        """Validate file permissions for the website."""
        try:
            critical_paths = [
                self.base_dir,
                os.path.join(self.base_dir, 'src'),
                os.path.join(self.base_dir, 'backend'),
                os.path.join(self.base_dir, 'public')
            ]
            
            valid_paths = 0
            invalid_paths = 0
            issues = []
            
            for path in critical_paths:
                if os.path.exists(path):
                    try:
                        stat_info = os.stat(path)
                        # Check if www-data can read and execute
                        if stat_info.st_mode & 0o755 == 0o755:
                            valid_paths += 1
                        else:
                            invalid_paths += 1
                            issues.append(f"Invalid permissions for {path}: {oct(stat_info.st_mode)}")
                    except Exception as e:
                        invalid_paths += 1
                        issues.append(f"Could not check {path}: {e}")
                else:
                    invalid_paths += 1
                    issues.append(f"Path does not exist: {path}")
            
            return {
                "success": invalid_paths == 0,
                "valid_paths": valid_paths,
                "invalid_paths": invalid_paths,
                "issues": issues
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def _check_npm_health(self) -> Dict[str, Any]:
        """Check npm package health and dependencies."""
        try:
            if not os.path.exists(self.base_dir):
                return {
                    "success": False,
                    "error": f"Base directory not found: {self.base_dir}"
                }
            
            # Check for package.json
            package_json = os.path.join(self.base_dir, 'package.json')
            if not os.path.exists(package_json):
                return {
                    "success": False,
                    "error": "package.json not found"
                }
            
            # Check for node_modules
            node_modules = os.path.join(self.base_dir, 'node_modules')
            if not os.path.exists(node_modules):
                return {
                    "success": False,
                    "error": "node_modules not found"
                }
            
            # Check for outdated packages
            result = subprocess.run(
                ["npm", "outdated", "--json"],
                cwd=self.base_dir,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            outdated_count = 0
            if result.returncode == 0 and result.stdout.strip():
                try:
                    outdated_data = json.loads(result.stdout)
                    outdated_count = len(outdated_data)
                except json.JSONDecodeError:
                    outdated_count = 0
            
            return {
                "success": True,
                "package_json_exists": True,
                "node_modules_exists": True,
                "outdated_packages": outdated_count,
                "npm_check_successful": result.returncode == 0
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
