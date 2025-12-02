"""
HOMESERVER Update Management System - Migrations Module
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
from typing import Dict, List, Any
from updates.index import log_message

class MigrationError(Exception):
    """Custom exception for migration operation failures."""
    pass

class MigrationManager:
    """Sequential migration manager with automatic retry on failure."""
    
    def __init__(self, module_path: str):
        self.module_path = Path(module_path)
        self.index_file = self.module_path / "index.json"
        self.config = self._load_config()
        self.src_dir = self.module_path / "src"
        self.log_file = Path("/var/log/homeserver/migrations.log")
        
        # Ensure log file exists
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self.log_file.touch(exist_ok=True)
        
    def _load_config(self) -> Dict[str, Any]:
        """Load the migrations configuration from index.json."""
        try:
            with open(self.index_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            log_message(f"Failed to load migrations config: {e}", "ERROR")
            return {}
    
    def _log_migration(self, message: str, level: str = "INFO"):
        """Log message to both unified system logger and migration-specific log file."""
        # Log through unified system logger first
        log_message(message, level)
        
        # Also write to migration-specific log file for historical record
        try:
            import datetime
            timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            log_entry = f"[{timestamp}] [{level}] {message}\n"
            with open(self.log_file, 'a') as f:
                f.write(log_entry)
        except Exception:
            # Don't fail if migration log file write fails
            pass
    
    def _should_run_migration(self, migration: Dict[str, Any]) -> bool:
        """Check if a migration should be executed."""
        # Only run if has_run is False
        has_run = migration.get('has_run', False)
        if has_run:
            migration_id = migration.get('id', 'unknown')
            self._log_migration(f"Migration {migration_id} has already run, skipping")
            return False
        return True
    
    def _execute_migration_script(self, migration: Dict[str, Any]) -> bool:
        """Execute the migration script for a migration."""
        migration_id = migration.get('id', 'unknown')
        script_name = f"{migration_id}.sh"
        script_path = self.src_dir / script_name
        
        if not script_path.exists():
            self._log_migration(f"Migration script not found: {script_path}", "ERROR")
            return False
        
        self._log_migration(f"Executing migration script: {script_name}")
        self._log_migration("=" * 60)
        
        try:
            # Make script executable
            os.chmod(script_path, 0o755)
            
            # Execute the script with timeout (10 minutes)
            result = subprocess.run(
                [str(script_path)],
                capture_output=True,
                text=True,
                timeout=600
            )
            
            # Log all output
            if result.stdout:
                self._log_migration(f"Migration output:\n{result.stdout}")
            
            if result.stderr:
                self._log_migration(f"Migration stderr:\n{result.stderr}", "WARNING")
            
            if result.returncode == 0:
                self._log_migration(f"Migration script {script_name} completed successfully")
                self._log_migration("=" * 60)
                return True
            else:
                self._log_migration(
                    f"Migration script {script_name} failed with return code {result.returncode}", 
                    "ERROR"
                )
                self._log_migration("=" * 60)
                return False
                
        except subprocess.TimeoutExpired:
            self._log_migration(f"Migration script {script_name} timed out after 10 minutes", "ERROR")
            self._log_migration("=" * 60)
            return False
        except Exception as e:
            self._log_migration(f"Error executing migration script {script_name}: {e}", "ERROR")
            self._log_migration("=" * 60)
            return False
    
    def _mark_migration_complete(self, migration_id: str) -> bool:
        """Mark a migration as completed by updating the index.json file."""
        try:
            # Update the config in memory
            for migration in self.config.get('migrations', []):
                if migration.get('id') == migration_id:
                    migration['has_run'] = True
                    break
            
            # Write the updated config back to disk
            with open(self.index_file, 'w') as f:
                json.dump(self.config, f, indent=2)
            
            self._log_migration(f"Marked migration {migration_id} as completed")
            return True
            
        except Exception as e:
            self._log_migration(f"Failed to mark migration {migration_id} as completed: {e}", "ERROR")
            return False
    
    def _process_migration(self, migration: Dict[str, Any]) -> bool:
        """Process a single migration with execution and state tracking."""
        migration_id = migration.get("id", "unknown")
        description = migration.get("description", migration_id)
        
        self._log_migration(f"Processing migration: {migration_id} - {description}")
        
        # Check if this migration should run
        if not self._should_run_migration(migration):
            return True  # Skip, not a failure
        
        # Execute the migration script
        script_success = self._execute_migration_script(migration)
        if not script_success:
            self._log_migration(
                f"Migration {migration_id} failed - will retry on next update cycle", 
                "ERROR"
            )
            return False
        
        # Mark migration as complete after successful execution
        mark_success = self._mark_migration_complete(migration_id)
        if not mark_success:
            self._log_migration(
                f"Migration {migration_id} executed but failed to mark as complete", 
                "WARNING"
            )
            # Still return True since the migration itself succeeded
        
        self._log_migration(f"Migration {migration_id} completed successfully")
        return True
    
    def run_migrations(self) -> Dict[str, Any]:
        """Run all pending migrations in sequential order."""
        self._log_migration("Starting migration execution...")
        self._log_migration("*" * 60)
        
        try:
            migrations = self.config.get("migrations", [])
            
            if not migrations:
                self._log_migration("No migrations found in configuration")
                return {"success": True, "migrations": [], "message": "No migrations to run"}
            
            self._log_migration(f"Found {len(migrations)} total migrations")
            
            # Count pending migrations
            pending_migrations = [m for m in migrations if not m.get('has_run', False)]
            self._log_migration(f"Found {len(pending_migrations)} pending migrations")
            
            if not pending_migrations:
                self._log_migration("All migrations have already run")
                return {
                    "success": True,
                    "migrations": [],
                    "total_migrations": len(migrations),
                    "message": "All migrations already completed"
                }
            
            # Process each migration in order
            migration_results = []
            successful_migrations = 0
            failed_migrations = 0
            
            for migration in migrations:
                migration_id = migration.get("id", "unknown")
                
                # Skip already completed migrations
                if migration.get('has_run', False):
                    continue
                
                try:
                    migration_success = self._process_migration(migration)
                    
                    migration_result = {
                        "migration_id": migration_id,
                        "description": migration.get("description", ""),
                        "success": migration_success
                    }
                    
                    if migration_success:
                        successful_migrations += 1
                        self._log_migration(f"✓ Migration {migration_id} succeeded")
                    else:
                        failed_migrations += 1
                        self._log_migration(f"✗ Migration {migration_id} failed", "ERROR")
                        migration_result["error"] = "Migration script failed"
                    
                    migration_results.append(migration_result)
                    
                except Exception as e:
                    self._log_migration(f"Unexpected error in migration {migration_id}: {e}", "ERROR")
                    failed_migrations += 1
                    migration_results.append({
                        "migration_id": migration_id,
                        "description": migration.get("description", ""),
                        "success": False,
                        "error": str(e)
                    })
            
            # Summary
            self._log_migration("*" * 60)
            self._log_migration(
                f"Migration execution complete: "
                f"{successful_migrations} successful, {failed_migrations} failed"
            )
            
            result = {
                "success": successful_migrations > 0 or failed_migrations == 0,
                "total_migrations": len(migrations),
                "pending_migrations": len(pending_migrations),
                "migrations_successful": successful_migrations,
                "migrations_failed": failed_migrations,
                "migration_results": migration_results
            }
            
            if successful_migrations > 0:
                result["message"] = (
                    f"Migrations completed: {successful_migrations}/{len(pending_migrations)} successful"
                )
            elif failed_migrations > 0:
                result["message"] = f"All {failed_migrations} pending migrations failed"
                result["error"] = "Migrations will retry on next update cycle"
            else:
                result["message"] = "No migrations executed"
            
            return result
            
        except Exception as e:
            self._log_migration(f"Migration system failed: {e}", "ERROR")
            return {
                "success": False,
                "error": str(e),
                "message": "Migration system encountered an unexpected error"
            }

def main(args=None):
    """
    Main entry point for migrations module.
    
    Args:
        args: List of arguments (supports '--check', '--version')
        
    Returns:
        dict: Status and results of the migration operation
    """
    if args is None:
        args = []
    
    # Get module path
    module_path = os.path.dirname(os.path.abspath(__file__))
    
    try:
        manager = MigrationManager(module_path)
        
        if "--check" in args:
            config = manager.config
            migrations = config.get("migrations", [])
            pending = [m for m in migrations if not m.get('has_run', False)]
            
            log_message(f"Migrations module status: {len(migrations)} total, {len(pending)} pending")
            return {
                "success": True,
                "total_migrations": len(migrations),
                "pending_migrations": len(pending),
                "schema_version": config.get("metadata", {}).get("schema_version", "unknown")
            }
        
        elif "--version" in args:
            config = manager.config
            schema_version = config.get("metadata", {}).get("schema_version", "unknown")
            log_message(f"Migrations module version: {schema_version}")
            return {
                "success": True,
                "schema_version": schema_version,
                "module": "migrations"
            }
        
        else:
            # Run migrations
            return manager.run_migrations()
            
    except Exception as e:
        log_message(f"Migrations module failed: {e}", "ERROR")
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    import sys
    result = main(sys.argv[1:])
    if not result.get("success", False):
        sys.exit(1)

