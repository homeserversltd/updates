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
HOMESERVER Website Update Module

Handles updating the HOMESERVER web interface from GitHub repository.
Supports selective component updates and automatic rollback on failure.
"""

import os
import sys
import json
import shutil
import subprocess
import tempfile
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import requests
import time

# Add the parent directory to the path to import GlobalRollback
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.GlobalRollback import GlobalRollback

class WebsiteUpdater:
    """Manages HOMESERVER website updates from GitHub repository."""
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize the website updater with configuration."""
        self.module_dir = Path(__file__).parent
        self.config_path = config_path or self.module_dir / "index.json"
        self.config = self._load_config()
        self.logger = self._setup_logging()
        self.rollback = GlobalRollback()
        
    def _load_config(self) -> Dict:
        """Load configuration from index.json."""
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            raise RuntimeError(f"Failed to load config from {self.config_path}: {e}")
    
    def _setup_logging(self) -> logging.Logger:
        """Set up logging for the updater."""
        logger = logging.getLogger('website_updater')
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger
    
    def _run_command(self, command: List[str], cwd: Optional[str] = None, 
                    timeout: int = 300) -> Tuple[bool, str, str]:
        """Run a shell command and return success status and output."""
        try:
            self.logger.info(f"Running command: {' '.join(command)}")
            result = subprocess.run(
                command,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            success = result.returncode == 0
            if not success:
                self.logger.error(f"Command failed with code {result.returncode}")
                self.logger.error(f"STDERR: {result.stderr}")
            
            return success, result.stdout, result.stderr
            
        except subprocess.TimeoutExpired:
            self.logger.error(f"Command timed out after {timeout} seconds")
            return False, "", "Command timed out"
        except Exception as e:
            self.logger.error(f"Command execution failed: {e}")
            return False, "", str(e)
    
    def _clone_repository(self) -> Optional[str]:
        """Clone the GitHub repository to temporary directory."""
        repo_config = self.config['config']['repository']
        temp_dir = repo_config['temp_directory']
        
        # Clean up existing temp directory
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        
        # Clone repository
        clone_cmd = [
            'git', 'clone', 
            '--branch', repo_config['branch'],
            '--depth', '1',  # Shallow clone for faster download
            repo_config['url'],
            temp_dir
        ]
        
        success, stdout, stderr = self._run_command(clone_cmd)
        if not success:
            self.logger.error(f"Failed to clone repository: {stderr}")
            return None
        
        self.logger.info(f"Successfully cloned repository to {temp_dir}")
        return temp_dir
    
    def _backup_current_installation(self) -> bool:
        """Create backup of current installation."""
        if not self.config['config']['backup']['enabled']:
            self.logger.info("Backup disabled, skipping")
            return True
        
        backup_config = self.config['config']['backup']
        include_paths = backup_config['include_paths']
        
        try:
            backup_id = self.rollback.create_backup(
                module_name='website',
                include_paths=include_paths,
                exclude_patterns=backup_config['exclude_patterns']
            )
            
            self.logger.info(f"Created backup with ID: {backup_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Backup failed: {e}")
            return False
    
    def _update_component(self, component_name: str, component_config: Dict, 
                         source_dir: str) -> bool:
        """Update a specific component (frontend, backend, premium, etc.)."""
        if not component_config.get('enabled', False):
            self.logger.info(f"Component {component_name} is disabled, skipping")
            return True
        
        source_path = os.path.join(source_dir, component_config['source_path'])
        target_path = component_config['target_path']
        
        if not os.path.exists(source_path):
            self.logger.warning(f"Source path {source_path} does not exist, skipping {component_name}")
            return True
        
        try:
            # Remove existing target directory
            if os.path.exists(target_path):
                shutil.rmtree(target_path)
            
            # Copy new content
            shutil.copytree(source_path, target_path)
            self.logger.info(f"Updated {component_name}: {source_path} -> {target_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to update {component_name}: {e}")
            return False
    
    def _run_build_process(self) -> bool:
        """Run the npm build process."""
        build_config = self.config['config']['build_process']
        base_dir = self.config['config']['target_paths']['base_directory']
        
        # Run pre-update commands
        for cmd in build_config.get('pre_update_commands', []):
            success, stdout, stderr = self._run_command(cmd.split(), cwd=base_dir)
            if not success:
                self.logger.error(f"Pre-update command failed: {cmd}")
                return False
        
        # Run npm install if enabled
        if build_config.get('npm_install', False):
            success, stdout, stderr = self._run_command(['npm', 'install'], cwd=base_dir)
            if not success:
                self.logger.error("npm install failed")
                return False
        
        # Run npm build if enabled
        if build_config.get('npm_build', False):
            success, stdout, stderr = self._run_command(['npm', 'run', 'build'], cwd=base_dir)
            if not success:
                self.logger.error("npm build failed")
                return False
        
        # Run post-update commands
        for cmd in build_config.get('post_update_commands', []):
            success, stdout, stderr = self._run_command(cmd.split(), cwd=base_dir)
            if not success:
                self.logger.error(f"Post-update command failed: {cmd}")
                return False
        
        return True
    
    def _verify_installation(self) -> bool:
        """Verify the installation was successful."""
        verification_config = self.config['config']['verification']
        
        # Check service status if enabled
        if verification_config.get('check_service_status', False):
            success, stdout, stderr = self._run_command(['systemctl', 'is-active', 'homeserver.service'])
            if not success:
                self.logger.error("homeserver.service is not active")
                return False
        
        # Health check if URL provided
        health_url = verification_config.get('health_check_url')
        if health_url:
            timeout = verification_config.get('health_check_timeout', 30)
            try:
                response = requests.get(health_url, timeout=timeout)
                if response.status_code != 200:
                    self.logger.error(f"Health check failed: HTTP {response.status_code}")
                    return False
                self.logger.info("Health check passed")
            except Exception as e:
                self.logger.error(f"Health check failed: {e}")
                return False
        
        return True
    
    def _cleanup_temp_directory(self, temp_dir: str):
        """Clean up temporary directory."""
        try:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
                self.logger.info(f"Cleaned up temporary directory: {temp_dir}")
        except Exception as e:
            self.logger.warning(f"Failed to clean up temp directory: {e}")
    
    def update(self) -> bool:
        """Perform the complete website update process."""
        if not self.config['metadata'].get('enabled', True):
            self.logger.info("Website updater is disabled")
            return True
        
        self.logger.info("Starting website update process")
        temp_dir = None
        
        try:
            # Step 1: Create backup
            if not self._backup_current_installation():
                return False
            
            # Step 2: Clone repository
            temp_dir = self._clone_repository()
            if not temp_dir:
                return False
            
            # Step 3: Update components
            components = self.config['config']['target_paths']['components']
            for component_name, component_config in components.items():
                if not self._update_component(component_name, component_config, temp_dir):
                    self.logger.error(f"Failed to update component: {component_name}")
                    if self.config['config']['rollback'].get('automatic_on_failure', True):
                        self.logger.info("Attempting automatic rollback")
                        self.rollback.rollback_module('website')
                    return False
            
            # Step 4: Run build process
            if not self._run_build_process():
                self.logger.error("Build process failed")
                if self.config['config']['rollback'].get('automatic_on_failure', True):
                    self.logger.info("Attempting automatic rollback")
                    self.rollback.rollback_module('website')
                return False
            
            # Step 5: Verify installation
            if not self._verify_installation():
                self.logger.error("Installation verification failed")
                if self.config['config']['rollback'].get('automatic_on_failure', True):
                    self.logger.info("Attempting automatic rollback")
                    self.rollback.rollback_module('website')
                return False
            
            self.logger.info("Website update completed successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Update process failed: {e}")
            if self.config['config']['rollback'].get('automatic_on_failure', True):
                self.logger.info("Attempting automatic rollback")
                self.rollback.rollback_module('website')
            return False
            
        finally:
            # Always cleanup temp directory
            if temp_dir:
                self._cleanup_temp_directory(temp_dir)
    
    def check_status(self) -> Dict:
        """Check the current status of the website installation."""
        status = {
            'module_enabled': self.config['metadata'].get('enabled', True),
            'components': {},
            'service_status': None,
            'last_update': None
        }
        
        # Check component status
        components = self.config['config']['target_paths']['components']
        for component_name, component_config in components.items():
            target_path = component_config['target_path']
            status['components'][component_name] = {
                'enabled': component_config.get('enabled', False),
                'exists': os.path.exists(target_path),
                'path': target_path
            }
        
        # Check service status
        try:
            success, stdout, stderr = self._run_command(['systemctl', 'is-active', 'homeserver.service'])
            status['service_status'] = 'active' if success else 'inactive'
        except:
            status['service_status'] = 'unknown'
        
        return status


def main():
    """Main entry point for the website updater."""
    import argparse
    
    parser = argparse.ArgumentParser(description='HOMESERVER Website Updater')
    parser.add_argument('--config', help='Path to configuration file')
    parser.add_argument('--update', action='store_true', help='Perform update')
    parser.add_argument('--status', action='store_true', help='Check status')
    parser.add_argument('--verify', action='store_true', help='Verify installation')
    
    args = parser.parse_args()
    
    try:
        updater = WebsiteUpdater(args.config)
        
        if args.update:
            success = updater.update()
            sys.exit(0 if success else 1)
        elif args.status:
            status = updater.check_status()
            print(json.dumps(status, indent=2))
        elif args.verify:
            success = updater._verify_installation()
            print(f"Verification: {'PASSED' if success else 'FAILED'}")
            sys.exit(0 if success else 1)
        else:
            parser.print_help()
            
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
