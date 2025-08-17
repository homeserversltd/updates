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
import json
import subprocess
import shutil
import urllib.request
import time
import re
import tempfile
from pathlib import Path
from updates.index import log_message
from updates.utils.state_manager import StateManager
from updates.utils.permissions import PermissionManager, PermissionTarget

# Load module configuration
def load_module_config():
    config_path = os.path.join(os.path.dirname(__file__), "index.json")
    with open(config_path, 'r') as f:
        return json.load(f)

MODULE_CONFIG = load_module_config()

# Configuration constants
DOCS_REPO_URL = "https://github.com/homeserversltd/documentation.git"
DOCS_LOCAL_PATH = "/opt/docs/docs"
DOCS_TEMP_PATH = "/tmp/homeserver-docs-update"
DOCS_VERSION_FILE = "/opt/docs/.docs_version"

def get_directories_config():
    return MODULE_CONFIG["config"]["directories"]

def get_mkdocs_paths():
    paths = []
    for dir_key, dir_config in get_directories_config().items():
        path = dir_config["path"]
        if os.path.exists(path):
            paths.append(path)
    return paths

def get_current_version():
    try:
        # Use the virtual environment's mkdocs
        result = subprocess.run(["/opt/docs/venv/bin/mkdocs", "--version"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            output = result.stdout.strip()
            pattern = r'mkdocs, version (\d+\.\d+\.\d+)'
            match = re.search(pattern, output)
            if match:
                version = match.group(1)
                log_message(f"Current MkDocs version: {version}", "INFO")
                return version
        log_message("Failed to get current MkDocs version", "WARNING")
        return None
    except Exception as e:
        log_message(f"Error getting current MkDocs version: {e}", "ERROR")
        return None

def get_latest_version():
    try:
        api_url = MODULE_CONFIG["config"]["installation"]["github_api_url"]
        with urllib.request.urlopen(api_url) as resp:
            data = json.load(resp)
            tag = data.get("tag_name", "")
            if tag.startswith("v"):
                return tag[1:]
            return tag
    except:
        return None

def get_current_docs_version():
    """Get the current documentation version from local storage."""
    try:
        # First try to read from the local VERSION file
        if os.path.exists(DOCS_VERSION_FILE):
            with open(DOCS_VERSION_FILE, 'r') as f:
                version = f.read().strip()
                log_message(f"Current local docs version: {version}", "INFO")
                return version
        
        # Fallback: try to read from index.json content_version
        try:
            with open(__file__.replace('index.py', 'index.json'), 'r') as f:
                config = json.load(f)
                content_version = config.get('metadata', {}).get('content_version')
                if content_version:
                    log_message(f"Current docs version from index.json: {content_version}", "INFO")
                    return content_version
        except:
            pass
        
        log_message("No local docs version found", "WARNING")
        return None
    except Exception as e:
        log_message(f"Failed to get current docs version: {e}", "ERROR")
        return None

def get_latest_docs_version():
    """Get the latest documentation version from the git repository."""
    try:
        # Create temp directory for git operations
        temp_dir = "/tmp/mkdocs-update"
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        
        # Clone the repository to get the latest VERSION
        result = subprocess.run([
            "git", "clone", "--depth", "1", 
            "https://github.com/homeserversltd/documentation.git", temp_dir
        ], capture_output=True, text=True, timeout=60)
        
        if result.returncode != 0:
            log_message(f"Git clone failed: {result.stderr}", "ERROR")
            return None
        
        # Read the VERSION file from the cloned repo
        version_file = os.path.join(temp_dir, "VERSION")
        if os.path.exists(version_file):
            with open(version_file, 'r') as f:
                version = f.read().strip()
            log_message(f"Latest remote docs version: {version}", "INFO")
            
            # Cleanup temp directory
            shutil.rmtree(temp_dir)
            return version
        else:
            log_message("VERSION file not found in remote repository", "ERROR")
            shutil.rmtree(temp_dir)
            return None
            
    except Exception as e:
        log_message(f"Failed to get latest docs version: {e}", "ERROR")
        # Cleanup temp directory if it exists
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        return None

def save_docs_version(version):
    """Save the current documentation version to local storage and update index.json."""
    try:
        # Save to VERSION file
        with open(DOCS_VERSION_FILE, 'w') as f:
            f.write(version)
        
        # Update content_version in index.json
        try:
            index_json_path = __file__.replace('index.py', 'index.json')
            with open(index_json_path, 'r') as f:
                config = json.load(f)
            
            config['metadata']['content_version'] = version
            
            with open(index_json_path, 'w') as f:
                json.dump(config, f, indent=4)
            
            log_message(f"Updated index.json content_version to {version}", "INFO")
        except Exception as e:
            log_message(f"Failed to update index.json content_version: {e}", "WARNING")
        
        return True
    except Exception as e:
        log_message(f"Failed to save docs version: {e}", "ERROR")
        return False

def clone_docs_repository():
    """Clone the documentation repository to temporary location."""
    try:
        # Clean up any existing temp directory
        if os.path.exists(DOCS_TEMP_PATH):
            shutil.rmtree(DOCS_TEMP_PATH)
        
        # Clone the repository
        result = subprocess.run([
            "git", "clone", "--depth", "1", 
            DOCS_REPO_URL, DOCS_TEMP_PATH
        ], capture_output=True, text=True, timeout=60)
        
        if result.returncode != 0:
            log_message(f"Git clone failed: {result.stderr}", "ERROR")
            return False
        
        return True
    except Exception as e:
        log_message(f"Failed to clone docs repository: {e}", "ERROR")
        return False

def deploy_docs_content_from_temp(temp_dir):
    """Deploy documentation content from temp location to docs directory."""
    try:
        # Ensure docs directory exists
        os.makedirs(DOCS_LOCAL_PATH, exist_ok=True)
        
        # Remove existing content (except .git if it exists)
        for item in os.listdir(DOCS_LOCAL_PATH):
            item_path = os.path.join(DOCS_LOCAL_PATH, item)
            if item != '.git':  # Preserve any git metadata
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path)
                else:
                    os.remove(item_path)
        
        # Copy new content from temp directory
        if os.path.exists(temp_dir):
            # Copy all files and directories except .git
            for item in os.listdir(temp_dir):
                if item != '.git':
                    src = os.path.join(temp_dir, item)
                    dst = os.path.join(DOCS_LOCAL_PATH, item)
                    if os.path.isdir(src):
                        shutil.copytree(src, dst)
                    else:
                        shutil.copy2(src, dst)
        
        # Set proper ownership and permissions
        admin_user = "admin"  # Default admin user
        try:
            # Get admin user from environment or config
            admin_user = os.environ.get('ADMIN_USER', 'admin')
        except:
            pass
        
        # Recursively set ownership
        for root, dirs, files in os.walk(DOCS_LOCAL_PATH):
            for d in dirs:
                path = os.path.join(root, d)
                subprocess.run(['chown', f'{admin_user}:{admin_user}', path], 
                             capture_output=True)
            for f in files:
                path = os.path.join(root, f)
                subprocess.run(['chown', f'{admin_user}:{admin_user}', path], 
                             capture_output=True)
        
        return True
    except Exception as e:
        log_message(f"Failed to deploy docs content: {e}", "ERROR")
        return False

def cleanup_temp_docs():
    """Clean up temporary documentation directory."""
    try:
        if os.path.exists(DOCS_TEMP_PATH):
            shutil.rmtree(DOCS_TEMP_PATH)
        return True
    except Exception as e:
        log_message(f"Failed to cleanup temp docs: {e}", "WARNING")
        return False

def update_documentation():
    """Update documentation content from git repository."""
    try:
        log_message("Checking for documentation updates...", "INFO")
        
        current_docs_version = get_current_docs_version()
        latest_docs_version = get_latest_docs_version()
        
        if not latest_docs_version:
            log_message("Could not determine latest docs version", "ERROR")
            return False
        
        if current_docs_version == latest_docs_version:
            log_message("Documentation is already up to date", "INFO")
            return True
        
        log_message(f"Updating documentation from {current_docs_version or 'unknown'} to {latest_docs_version}", "INFO")
        
        # Clone repository to temp location
        temp_dir = "/tmp/mkdocs-update"
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        
        log_message("Cloning documentation repository...", "INFO")
        result = subprocess.run([
            "git", "clone", "--depth", "1", 
            "https://github.com/homeserversltd/documentation.git", temp_dir
        ], capture_output=True, text=True, timeout=120)
        
        if result.returncode != 0:
            log_message(f"Git clone failed: {result.stderr}", "ERROR")
            return False
        
        # Deploy content from temp directory
        log_message("Deploying new documentation content...", "INFO")
        if not deploy_docs_content_from_temp(temp_dir):
            shutil.rmtree(temp_dir)
            return False
        
        # Save new version
        if not save_docs_version(latest_docs_version):
            log_message("Failed to save docs version, but content updated", "WARNING")
        
        # Cleanup
        shutil.rmtree(temp_dir)
        log_message("Documentation updated successfully", "INFO")
        return True
        
    except Exception as e:
        log_message(f"Documentation update failed: {e}", "ERROR")
        # Cleanup temp directory if it exists
        if 'temp_dir' in locals() and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        return False

def restore_mkdocs_permissions():
    try:
        permission_manager = PermissionManager("mkdocs")
        targets = []
        default_owner = MODULE_CONFIG["config"]["permissions"]["owner"]
        default_group = MODULE_CONFIG["config"]["permissions"]["group"]
        
        for dir_key, dir_config in get_directories_config().items():
            targets.append(PermissionTarget(
                path=dir_config["path"],
                owner=default_owner,
                group=default_group,
                mode=int(dir_config["mode"], 8),
                recursive=True
            ))
        
        return permission_manager.set_permissions(targets)
    except Exception as e:
        log_message(f"Failed to restore permissions: {e}", "ERROR")
        return False

def verify_mkdocs_installation():
    verification = {
        "pip_installed": False,
        "version": None,
        "service_active": False,
        "docs_version": None
    }
    try:
        verification["version"] = get_current_version()
        verification["pip_installed"] = verification["version"] is not None
        verification["service_active"] = is_service_active("mkdocs")
        verification["docs_version"] = get_current_docs_version()
    except:
        pass
    return verification

def is_service_active(service):
    try:
        result = subprocess.run(["systemctl", "is-active", "--quiet", service])
        return result.returncode == 0
    except:
        return False

def systemctl(action, service="mkdocs"):
    try:
        result = subprocess.run(["systemctl", action, service], capture_output=True, text=True)
        return result.returncode == 0
    except:
        return False

def main(args=None):
    if args is None:
        args = []
    
    # Module directory for reference
    module_dir = Path(__file__).parent
    
    log_message("Starting mkdocs update...")
    
    # Check for software updates
    current_version = get_current_version()
    latest_version = get_latest_version()
    
    # Check for documentation updates
    current_docs_version = get_current_docs_version()
    latest_docs_version = get_latest_docs_version()
    
    software_needs_update = current_version != latest_version
    # Only try to update docs if we can successfully get the latest version
    docs_need_update = latest_docs_version is not None and current_docs_version != latest_docs_version
    
    if not software_needs_update and not docs_need_update:
        verification = verify_mkdocs_installation()
        return {"success": True, "updated": False, "verification": verification}
    
    # Backup current state if either component needs updating
    state_manager = StateManager()
    files_to_backup = get_mkdocs_paths() + [DOCS_LOCAL_PATH, DOCS_VERSION_FILE]
    backup_success = state_manager.backup_module_state(
        "mkdocs",
        f"pre_update_{current_version or 'unknown'}_to_{latest_version or 'unknown'}_docs_{current_docs_version or 'unknown'}_to_{latest_docs_version or 'unknown'}",
        files=files_to_backup
    )
    if not backup_success:
        return {"success": False, "error": "Backup failed"}
    
    try:
        # Stop service before updates
        systemctl("stop")
        
        # Update software if needed
        if software_needs_update:
            log_message(f"Updating MkDocs software from {current_version} to {latest_version}", "INFO")
            subprocess.run(["/opt/docs/venv/bin/pip", "install", "--upgrade", "mkdocs"], check=True)
            subprocess.run(["/opt/docs/venv/bin/pip", "install", "--upgrade", "mkdocs-material"], check=True)
        
        # Update documentation if needed
        if docs_need_update:
            if not update_documentation():
                raise Exception("Documentation update failed")
        
        # Restore permissions
        restore_mkdocs_permissions()
        
        # Start service
        systemctl("start")
        time.sleep(5)  # Wait for startup
        
        # Verify everything is working
        verification = verify_mkdocs_installation()
        new_version = verification.get("version")
        new_docs_version = verification.get("docs_version")
        
        success_conditions = [
            # For software updates: either no update needed, or software is working (version check is lenient)
            not software_needs_update or (new_version is not None and verification["pip_installed"]),
            # For docs updates: either no update needed, or docs version matches
            not docs_need_update or (latest_docs_version is not None and new_docs_version == latest_docs_version),
            # Service must be active
            verification["service_active"]
        ]
        
        if all(success_conditions):
            log_message("MkDocs update completed successfully", "INFO")
            return {
                "success": True, 
                "updated": True, 
                "verification": verification,
                "software_updated": software_needs_update,
                "docs_updated": docs_need_update
            }
        else:
            raise Exception("Post-update verification failed")
            
    except Exception as e:
        log_message(f"Update failed: {e}", "ERROR")
        state_manager.restore_module_state("mkdocs")
        systemctl("start")
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    main()