"""
HOMESERVER Update Management System
Copyright (C) 2024 HOMESERVER LLC

Maintenance Runner Utility

This utility discovers and runs maintenance tasks from all modules that have maintenance.py files.
Maintenance tasks are ALWAYS executed as part of the update process to ensure system health
and dependency freshness. This is NOT a standalone maintenance system.
"""

import os
import json
import importlib
from typing import Dict, Any, List, Optional
from pathlib import Path
from .index import log_message


class MaintenanceRunner:
    """Discovers and runs maintenance tasks from all modules as part of the update process.
    
    Maintenance tasks are ALWAYS executed during updates to ensure system health
    and dependency freshness. This is not a standalone maintenance system.
    """
    
    def __init__(self, modules_path: str = "/usr/local/lib/updates"):
        self.modules_path = Path(modules_path)
        self.maintenance_registry = {}
        self._discover_maintenance_modules()
    
    def _discover_maintenance_modules(self) -> None:
        """Discover all available maintenance modules."""
        log_message("Discovering maintenance modules...")
        
        # Check both possible module locations
        modules_search_path = self.modules_path / "modules"
        if not modules_search_path.exists():
            modules_search_path = self.modules_path
        
        if not modules_search_path.exists():
            log_message("No modules directory found", "WARNING")
            return
        
        discovered_count = 0
        
        for item in os.listdir(modules_search_path):
            item_path = modules_search_path / item
            
            # Skip non-directories and backup directories
            if not item_path.is_dir() or item.endswith('.backup'):
                continue
            
            # Check if module has maintenance.py
            maintenance_file = item_path / "maintenance.py"
            if not maintenance_file.exists():
                continue
            
            # Check if module is enabled
            index_file = item_path / "index.json"
            if index_file.exists():
                try:
                    with open(index_file, 'r') as f:
                        config = json.load(f)
                    
                    enabled = config.get("metadata", {}).get("enabled", True)
                    if not enabled:
                        log_message(f"Module {item} is disabled, skipping maintenance", "DEBUG")
                        continue
                        
                except Exception as e:
                    log_message(f"Error reading config for {item}: {e}", "WARNING")
                    continue
            
            # Try to import the maintenance module
            try:
                module_path = f"modules.{item}.maintenance"
                maintenance_module = importlib.import_module(module_path)
                
                # Look for the maintenance class (e.g., WebsiteMaintenance, AdblockMaintenance)
                maintenance_class = None
                for attr_name in dir(maintenance_module):
                    attr = getattr(maintenance_module, attr_name)
                    if (isinstance(attr, type) and 
                        attr_name.endswith('Maintenance') and
                        hasattr(attr, 'run_maintenance')):
                        
                        maintenance_class = attr
                        break
                
                if maintenance_class:
                    # Load module config
                    module_config = self._load_module_config(item_path)
                    self.maintenance_registry[item] = {
                        "class": maintenance_class,
                        "config": module_config,
                        "path": str(item_path)
                    }
                    discovered_count += 1
                    log_message(f"✓ Found maintenance module: {item}")
                else:
                    log_message(f"Module {item} has maintenance.py but no valid maintenance class", "WARNING")
                    
            except ImportError as e:
                log_message(f"Failed to import maintenance for {item}: {e}", "WARNING")
            except Exception as e:
                log_message(f"Error discovering maintenance for {item}: {e}", "WARNING")
        
        log_message(f"Discovered {discovered_count} maintenance modules")
    
    def _load_module_config(self, module_path: Path) -> Dict[str, Any]:
        """Load module configuration from index.json."""
        try:
            index_file = module_path / "index.json"
            if index_file.exists():
                with open(index_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            log_message(f"Failed to load config for {module_path.name}: {e}", "WARNING")
        
        return {}
    
    def run_all_maintenance(self) -> Dict[str, Any]:
        """Run maintenance for all discovered modules."""
        results = {
            "success": True,
            "modules": {},
            "summary": {
                "total_modules": len(self.maintenance_registry),
                "successful": 0,
                "failed": 0,
                "skipped": 0
            }
        }
        
        if not self.maintenance_registry:
            log_message("No maintenance modules found to run")
            return results
        
        log_message(f"Running maintenance for {len(self.maintenance_registry)} modules...")
        
        for module_name, module_info in self.maintenance_registry.items():
            try:
                log_message(f"Running maintenance for {module_name}...")
                
                # Create maintenance instance and run
                maintenance_instance = module_info["class"](module_info["config"])
                module_result = maintenance_instance.run_maintenance()
                
                results["modules"][module_name] = module_result
                
                if module_result.get("success", False):
                    results["summary"]["successful"] += 1
                    log_message(f"✓ Maintenance completed for {module_name}")
                else:
                    results["summary"]["failed"] += 1
                    error_msg = module_result.get("error", "Unknown error")
                    log_message(f"✗ Maintenance failed for {module_name}: {error_msg}", "ERROR")
                    
            except Exception as e:
                log_message(f"✗ Maintenance crashed for {module_name}: {e}", "ERROR")
                results["modules"][module_name] = {
                    "success": False,
                    "error": str(e),
                    "crashed": True
                }
                results["summary"]["failed"] += 1
        
        # Overall success depends on all modules succeeding
        results["success"] = results["summary"]["failed"] == 0
        
        log_message(f"Maintenance completed: {results['summary']['successful']} successful, {results['summary']['failed']} failed")
        return results
    
    def run_module_maintenance(self, module_name: str) -> Optional[Dict[str, Any]]:
        """Run maintenance for a specific module."""
        if module_name not in self.maintenance_registry:
            log_message(f"Module {module_name} has no maintenance capability", "WARNING")
            return None
        
        try:
            log_message(f"Running maintenance for {module_name}...")
            
            module_info = self.maintenance_registry[module_name]
            maintenance_instance = module_info["class"](module_info["config"])
            
            result = maintenance_instance.run_maintenance()
            
            if result.get("success", False):
                log_message(f"✓ Maintenance completed for {module_name}")
            else:
                error_msg = result.get("error", "Unknown error")
                log_message(f"✗ Maintenance failed for {module_name}: {error_msg}", "ERROR")
            
            return result
            
        except Exception as e:
            log_message(f"✗ Maintenance crashed for {module_name}: {e}", "ERROR")
            return {
                "success": False,
                "error": str(e),
                "crashed": True
            }
    
    def list_maintenance_modules(self) -> List[str]:
        """List all modules that have maintenance capability."""
        return list(self.maintenance_registry.keys())
    
    def get_maintenance_status(self) -> Dict[str, Any]:
        """Get status of all maintenance modules."""
        status = {
            "total_modules": len(self.maintenance_registry),
            "modules": {}
        }
        
        for module_name, module_info in self.maintenance_registry.items():
            status["modules"][module_name] = {
                "has_maintenance": True,
                "config_loaded": bool(module_info["config"]),
                "path": module_info["path"]
            }
        
        return status


# Convenience functions for easy import
def create_maintenance_runner(modules_path: str = "/usr/local/lib/updates") -> MaintenanceRunner:
    """Create a MaintenanceRunner instance."""
    return MaintenanceRunner(modules_path)


def run_all_maintenance(modules_path: str = "/usr/local/lib/updates") -> Dict[str, Any]:
    """Run maintenance for all modules as part of the update process."""
    runner = MaintenanceRunner(modules_path)
    return runner.run_all_maintenance()


def run_module_maintenance(module_name: str, modules_path: str = "/usr/local/lib/updates") -> Optional[Dict[str, Any]]:
    """Run maintenance for a specific module."""
    runner = MaintenanceRunner(modules_path)
    return runner.run_module_maintenance(module_name)


def list_maintenance_modules(modules_path: str = "/usr/local/lib/updates") -> List[str]:
    """List all modules with maintenance capability."""
    runner = MaintenanceRunner(modules_path)
    return runner.list_maintenance_modules()
