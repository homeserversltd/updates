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
Version Control utility for the update orchestration system.

This module provides functionality to checkout different versions of update modules
using Git tags and the manifest version information.
"""

import os
import json
import subprocess
from typing import Optional, Dict, Any
from .index import log_message

def get_git_root() -> str:
    """Get the root directory of the Git repository."""
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--show-toplevel'],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to get Git root: {e}")

def load_manifest() -> Dict[str, Any]:
    """Load the manifest file."""
    manifest_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'manifest.json')
    with open(manifest_path, 'r') as f:
        return json.load(f)

def get_module_tags(module_name: str) -> list[str]:
    """Get all Git tags for a specific module."""
    try:
        result = subprocess.run(
            ['git', 'tag', '-l', f'{module_name}-v*'],
            capture_output=True,
            text=True,
            check=True
        )
        return sorted(result.stdout.strip().split('\n'))
    except subprocess.CalledProcessError as e:
        log_message(f"Failed to get tags for {module_name}: {e}", "ERROR")
        return []

def checkout_module_version(module_name: str, target_version: Optional[str] = None) -> bool:
    """
    Checkout a module to a specific version or its lastSafeVersion.
    
    Args:
        module_name: Name of the module to checkout
        target_version: Specific version to checkout to. If None, uses lastSafeVersion from manifest
        
    Returns:
        bool: True if checkout successful, False otherwise
    """
    try:
        manifest = load_manifest()
        module_info = next((m for m in manifest['updates'] if m['name'] == module_name), None)
        
        if not module_info:
            log_message(f"Module {module_name} not found in manifest", "ERROR")
            return False
            
        # Determine target version
        version = target_version or module_info.get('lastSafeVersion')
        if not version:
            log_message(f"No target version specified and no lastSafeVersion found for {module_name}", "ERROR")
            return False
            
        # Find matching tag
        tags = get_module_tags(module_name)
        target_tag = next((t for t in reversed(tags) if f'{module_name}-v{version}-' in t), None)
        
        if not target_tag:
            log_message(f"No tag found for {module_name} version {version}", "ERROR")
            return False
            
        # Get module path relative to git root
        git_root = get_git_root()
        module_path = os.path.join('initialization/files/user_local_lib/updates', module_name)
        
        # Checkout the specific version for this module
        result = subprocess.run(
            ['git', 'checkout', target_tag, '--', module_path],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            log_message(f"Failed to checkout {target_tag}: {result.stderr}", "ERROR")
            return False
            
        log_message(f"Successfully checked out {module_name} to version {version}")
        return True
        
    except Exception as e:
        log_message(f"Error during checkout of {module_name}: {e}", "ERROR")
        return False

def list_module_versions(module_name: str) -> list[Dict[str, str]]:
    """
    List all available versions for a module.
    
    Returns a list of dicts with version info:
    [{'tag': 'module-v1.0.0-20240610', 'version': '1.0.0', 'timestamp': '20240610'}]
    """
    tags = get_module_tags(module_name)
    versions = []
    
    for tag in tags:
        # Parse tag format: module-v1.0.0-20240610
        parts = tag.split('-')
        if len(parts) == 3:
            versions.append({
                'tag': tag,
                'version': parts[1][1:],  # Remove 'v' prefix
                'timestamp': parts[2]
            })
    
    return versions

def checkout_last_safe(module_name: str) -> bool:
    """
    Convenience function to checkout lastSafeVersion.
    """
    return checkout_module_version(module_name) 