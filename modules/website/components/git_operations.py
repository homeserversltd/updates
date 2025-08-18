"""
HOMESERVER Website Update Components
Copyright (C) 2024 HOMESERVER LLC

Git Operations Component

Handles all Git repository operations for the website update system including:
- Repository cloning and validation
- Version retrieval from repository files
- Temporary directory management
- Repository cleanup operations
"""

import os
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional
from updates.index import log_message


class GitOperations:
    """Handles Git repository operations for website updates."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.repo_config = config.get('config', {}).get('repository', {})
        
    def clone_repository(self) -> Optional[str]:
        """
        Clone the website repository to a temporary directory.
        
        Returns:
            Optional[str]: Path to the cloned repository, or None if failed
        """
        repo_url = self.repo_config.get('url', 'https://github.com/homeserversltd/website.git')
        branch = self.repo_config.get('branch', 'master')
        temp_base = self.repo_config.get('temp_directory', '/tmp/homeserver-website-update')
        
        log_message(f"[GIT] Cloning repository: {repo_url} (branch: {branch})")
        
        try:
            # Clean up any existing temp directory
            if os.path.exists(temp_base):
                shutil.rmtree(temp_base)
                log_message(f"[GIT] Cleaned up existing temp directory: {temp_base}")
            
            # Create fresh temporary directory
            os.makedirs(temp_base, exist_ok=True)
            
            # Clone repository with shallow clone for efficiency
            clone_cmd = [
                'git', 'clone',
                '--depth', '1',
                '--branch', branch,
                repo_url,
                temp_base
            ]
            
            log_message(f"[GIT] Running: {' '.join(clone_cmd)}")
            
            result = subprocess.run(
                clone_cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode != 0:
                log_message(f"[GIT] Clone failed: {result.stderr}", "ERROR")
                return None
            
            # Verify clone was successful
            if not self._validate_repository(temp_base):
                log_message("[GIT] Repository validation failed", "ERROR")
                return None
            
            log_message(f"[GIT] ✓ Repository cloned successfully to: {temp_base}")
            return temp_base
            
        except subprocess.TimeoutExpired:
            log_message("[GIT] Repository clone timed out", "ERROR")
            return None
        except Exception as e:
            log_message(f"[GIT] Clone failed with exception: {e}", "ERROR")
            return None
    
    def _validate_repository(self, repo_path: str) -> bool:
        """
        Validate that the cloned repository contains expected files.
        
        Args:
            repo_path: Path to the repository to validate
            
        Returns:
            bool: True if repository is valid, False otherwise
        """
        required_files = [
            'src',  # Frontend source directory
            'backend',  # Backend API directory
            'package.json',  # NPM configuration
            'main.py'  # Flask main file
        ]
        
        log_message("[GIT] Validating repository structure...")
        
        for required_file in required_files:
            file_path = os.path.join(repo_path, required_file)
            if not os.path.exists(file_path):
                log_message(f"[GIT] ✗ Missing required file/directory: {required_file}", "ERROR")
                return False
            log_message(f"[GIT] ✓ Found: {required_file}")
        
        log_message("[GIT] ✓ Repository structure is valid")
        return True
    
    def get_repository_version(self, repo_path: str) -> Optional[str]:
        """
        Get the version from the repository's homeserver.json file.
        
        Args:
            repo_path: Path to the cloned repository
            
        Returns:
            Optional[str]: Version string, or None if not found
        """
        try:
            # Hardcoded version file and path
            version_file = 'src/config/homeserver.json'
            version_path_components = 'global.version.version'.split('.')
            
            repo_config_path = os.path.join(repo_path, version_file)
            
            log_message(f"[GIT] Reading version from: {repo_config_path}")
            
            if not os.path.exists(repo_config_path):
                log_message(f"[GIT] Repository version file not found: {version_file}", "WARNING")
                return None
            
            with open(repo_config_path, 'r') as f:
                config_data = json.load(f)
            
            # Navigate through the nested path (e.g., global.version.version)
            version = config_data
            for component in version_path_components:
                if isinstance(version, dict) and component in version:
                    version = version[component]
                else:
                    log_message(f"[GIT] Version path {'.'.join(version_path_components)} not found", "WARNING")
                    return None
            
            if isinstance(version, str):
                log_message(f"[GIT] ✓ Repository version: {version}")
                return version
            else:
                log_message(f"[GIT] Version is not a string: {version}", "WARNING")
                return None
                
        except Exception as e:
            log_message(f"[GIT] Failed to read repository version: {e}", "ERROR")
            return None
    
    def cleanup_repository(self, repo_path: str) -> None:
        """
        Clean up the temporary repository directory.
        
        Args:
            repo_path: Path to the repository to clean up
        """
        if repo_path and os.path.exists(repo_path):
            try:
                shutil.rmtree(repo_path)
                log_message(f"[GIT] ✓ Cleaned up repository: {repo_path}")
            except Exception as e:
                log_message(f"[GIT] Failed to cleanup repository {repo_path}: {e}", "WARNING")
        else:
            log_message("[GIT] No repository to cleanup")
    
    def get_git_info(self, repo_path: str) -> Dict[str, str]:
        """
        Get Git information about the repository.
        
        Args:
            repo_path: Path to the repository
            
        Returns:
            Dict[str, str]: Git information (commit hash, branch, etc.)
        """
        git_info = {}
        
        try:
            # Get current commit hash
            result = subprocess.run(
                ['git', 'rev-parse', 'HEAD'],
                cwd=repo_path,
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                git_info['commit'] = result.stdout.strip()
            
            # Get current branch
            result = subprocess.run(
                ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
                cwd=repo_path,
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                git_info['branch'] = result.stdout.strip()
            
            # Get remote URL
            result = subprocess.run(
                ['git', 'remote', 'get-url', 'origin'],
                cwd=repo_path,
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                git_info['remote'] = result.stdout.strip()
            
            log_message(f"[GIT] Repository info: {git_info}")
            
        except Exception as e:
            log_message(f"[GIT] Failed to get git info: {e}", "WARNING")
        
        return git_info
