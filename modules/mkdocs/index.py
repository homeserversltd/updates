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
from typing import Tuple, Dict, Any

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

def get_current_mkdocs_version():
    """Get the current MkDocs software version from the virtual environment."""
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

def get_current_material_theme_version():
    """Get the current MkDocs Material theme version from the virtual environment."""
    try:
        # Use pip to get the installed version of mkdocs-material
        result = subprocess.run(["/opt/docs/venv/bin/pip", "show", "mkdocs-material"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            output = result.stdout.strip()
            pattern = r'Version: (\d+\.\d+\.\d+)'
            match = re.search(pattern, output)
            if match:
                version = match.group(1)
                log_message(f"Current Material theme version: {version}", "INFO")
                return version
        log_message("Failed to get current Material theme version", "WARNING")
        return None
    except Exception as e:
        log_message(f"Error getting current Material theme version: {e}", "ERROR")
        return None

def get_latest_mkdocs_version():
    """Get the latest MkDocs software version from GitHub API."""
    try:
        api_url = MODULE_CONFIG["config"]["installation"]["mkdocs_repo"]
        with urllib.request.urlopen(api_url) as resp:
            data = json.load(resp)
            tag = data.get("tag_name", "")
            if tag.startswith("v"):
                return tag[1:]
            return tag
    except Exception as e:
        log_message(f"Failed to get latest MkDocs version: {e}", "WARNING")
        return None

def get_latest_material_theme_version():
    """Get the latest MkDocs Material theme version from GitHub API."""
    try:
        api_url = MODULE_CONFIG["config"]["installation"]["material_theme_repo"]
        with urllib.request.urlopen(api_url) as resp:
            data = json.load(resp)
            tag = data.get("tag_name", "")
            if tag.startswith("v"):
                return tag[1:]
            return tag
    except Exception as e:
        log_message(f"Failed to get latest Material theme version: {e}", "WARNING")
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
        
        # Clone the repository to get the latest VERSION (public repo, no credentials needed)
        env = os.environ.copy()
        env['GIT_TERMINAL_PROMPT'] = '0'
        result = subprocess.run([
            "git", "clone", "--depth", "1", 
            "https://github.com/homeserversltd/documentation.git", temp_dir
        ], capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL, env=env)
        
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

def save_versions(mkdocs_version, material_theme_version, docs_version):
    """Save all current versions to index.json."""
    try:
        # Update versions in index.json
        try:
            index_json_path = __file__.replace('index.py', 'index.json')
            with open(index_json_path, 'r') as f:
                config = json.load(f)
            
            config['metadata']['mkdocs_version'] = mkdocs_version
            config['metadata']['material_theme_version'] = material_theme_version
            config['metadata']['content_version'] = docs_version
            
            with open(index_json_path, 'w') as f:
                json.dump(config, f, indent=4)
            
            log_message(f"Updated index.json versions: mkdocs={mkdocs_version}, theme={material_theme_version}, docs={docs_version}", "INFO")
        except Exception as e:
            log_message(f"Failed to update index.json versions: {e}", "WARNING")
        
        # Save docs version to VERSION file
        if docs_version:
            try:
                with open(DOCS_VERSION_FILE, 'w') as f:
                    f.write(docs_version)
            except Exception as e:
                log_message(f"Failed to save docs VERSION file: {e}", "WARNING")
        
        return True
    except Exception as e:
        log_message(f"Failed to save versions: {e}", "ERROR")
        return False

def _check_version_update_needed() -> Tuple[bool, bool, bool, Dict[str, Any]]:
    """
    Check if updates are needed by comparing local versions with remote versions.
    
    Returns:
        Tuple[bool, bool, bool, Dict]: (mkdocs_update_needed, theme_update_needed, docs_update_needed, version_info)
    """
    try:
        # Get current versions from index.json
        module_dir = Path(__file__).parent
        cfg = load_module_config()
        local_mkdocs_version = cfg.get('metadata', {}).get('mkdocs_version', '0.0.0')
        local_theme_version = cfg.get('metadata', {}).get('material_theme_version', '0.0.0')
        local_docs_version = cfg.get('metadata', {}).get('content_version', '0.0.0')
        
        log_message(f"Local versions - MkDocs: {local_mkdocs_version}, Theme: {local_theme_version}, Docs: {local_docs_version}")
        
        # Get remote versions
        remote_mkdocs_version = get_latest_mkdocs_version()
        remote_theme_version = get_latest_material_theme_version()
        remote_docs_version = get_latest_docs_version()
        
        log_message(f"Remote versions - MkDocs: {remote_mkdocs_version}, Theme: {remote_theme_version}, Docs: {remote_docs_version}")
        
        # Determine what needs updating
        mkdocs_update_needed = (remote_mkdocs_version and local_mkdocs_version != remote_mkdocs_version)
        theme_update_needed = (remote_theme_version and local_theme_version != remote_theme_version)
        docs_update_needed = (remote_docs_version and local_docs_version != remote_docs_version)
        
        version_info = {
            "local": {
                "mkdocs": local_mkdocs_version,
                "theme": local_theme_version,
                "docs": local_docs_version
            },
            "remote": {
                "mkdocs": remote_mkdocs_version,
                "theme": remote_theme_version,
                "docs": remote_docs_version
            },
            "updates_needed": {
                "mkdocs": mkdocs_update_needed,
                "theme": theme_update_needed,
                "docs": docs_update_needed
            }
        }
        
        if not any([mkdocs_update_needed, theme_update_needed, docs_update_needed]):
            log_message("All components are up to date, no updates needed")
        else:
            if mkdocs_update_needed:
                log_message(f"MkDocs software update needed: {local_mkdocs_version} → {remote_mkdocs_version}")
            if theme_update_needed:
                log_message(f"Material theme update needed: {local_theme_version} → {remote_theme_version}")
            if docs_update_needed:
                log_message(f"Documentation update needed: {local_docs_version} → {remote_docs_version}")
        
        return mkdocs_update_needed, theme_update_needed, docs_update_needed, version_info
        
    except Exception as e:
        log_message(f"Version check failed: {e}, assuming updates needed", "WARNING")
        return True, True, True, {}

def check(module_dir: Path) -> Dict[str, Any]:
    """Check mode - return current status without performing updates."""
    try:
        mkdocs_update_needed, theme_update_needed, docs_update_needed, version_info = _check_version_update_needed()
        
        # Get current installation status
        verification = verify_mkdocs_installation()
        
        return {
            'success': True,
            'updated': False,
            'verification': verification,
            'version_info': version_info,
            'updates_available': {
                'mkdocs': mkdocs_update_needed,
                'theme': theme_update_needed,
                'docs': docs_update_needed
            }
        }
        
    except Exception as e:
        log_message(f"Check failed: {e}", "ERROR")
        return {'success': False, 'error': str(e)}

def clone_docs_repository():
    """Clone the documentation repository to temporary location."""
    try:
        # Clean up any existing temp directory
        if os.path.exists(DOCS_TEMP_PATH):
            shutil.rmtree(DOCS_TEMP_PATH)
        
        # Clone the repository (public repo, no credentials needed)
        env = os.environ.copy()
        env['GIT_TERMINAL_PROMPT'] = '0'
        result = subprocess.run([
            "git", "clone", "--depth", "1", 
            DOCS_REPO_URL, DOCS_TEMP_PATH
        ], capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL, env=env)
        
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
        
        # Copy new content from temp directory's docs/ subdirectory
        if os.path.exists(temp_dir):
            # The temp directory contains the git repo, we want the docs/ subdirectory
            docs_source_dir = os.path.join(temp_dir, "docs")
            if os.path.exists(docs_source_dir):
                # Copy all files and directories from docs/ subdirectory
                items_copied = []
                items_failed = []
                for item in os.listdir(docs_source_dir):
                    src = os.path.join(docs_source_dir, item)
                    dst = os.path.join(DOCS_LOCAL_PATH, item)
                    try:
                        if os.path.isdir(src):
                            # Remove destination if it exists (shouldn't after cleanup, but be safe)
                            if os.path.exists(dst):
                                shutil.rmtree(dst)
                            shutil.copytree(src, dst)
                            log_message(f"Copied directory: {item}", "INFO")
                        else:
                            shutil.copy2(src, dst)
                            log_message(f"Copied file: {item}", "INFO")
                        items_copied.append(item)
                    except Exception as e:
                        log_message(f"Failed to copy {item}: {e}", "ERROR")
                        items_failed.append(item)
                
                if items_failed:
                    log_message(f"Failed to copy {len(items_failed)} items: {', '.join(items_failed)}", "ERROR")
                    return False
                
                log_message(f"Successfully copied {len(items_copied)} items from repository", "INFO")
            else:
                log_message(f"docs/ subdirectory not found in temp directory: {temp_dir}", "ERROR")
                return False
            
            # Copy mkdocs.yml from temp directory root to /opt/docs/
            mkdocs_yml_src = os.path.join(temp_dir, "mkdocs.yml")
            mkdocs_yml_dst = "/opt/docs/mkdocs.yml"
            if os.path.exists(mkdocs_yml_src):
                shutil.copy2(mkdocs_yml_src, mkdocs_yml_dst)
                log_message("Copied mkdocs.yml to /opt/docs/", "INFO")
            else:
                log_message("mkdocs.yml not found in temp directory", "WARNING")
            
            # Copy VERSION file from temp directory root to /opt/docs/
            version_src = os.path.join(temp_dir, "VERSION")
            version_dst = "/opt/docs/VERSION"
            if os.path.exists(version_src):
                shutil.copy2(version_src, version_dst)
                log_message("Copied VERSION to /opt/docs/", "INFO")
            else:
                log_message("VERSION file not found in temp directory", "WARNING")
        
        # Set proper ownership and permissions
        admin_user = "admin"  # Default admin user
        try:
            # Get admin user from environment or config
            admin_user = os.environ.get('ADMIN_USER', 'admin')
        except:
            pass
        
        # Recursively set ownership for docs directory
        for root, dirs, files in os.walk(DOCS_LOCAL_PATH):
            for d in dirs:
                path = os.path.join(root, d)
                subprocess.run(['chown', f'{admin_user}:{admin_user}', path], 
                             capture_output=True)
            for f in files:
                path = os.path.join(root, f)
                subprocess.run(['chown', f'{admin_user}:{admin_user}', path], 
                             capture_output=True)
        
        # Set ownership for mkdocs.yml and VERSION files
        for file_path in ["/opt/docs/mkdocs.yml", "/opt/docs/VERSION"]:
            if os.path.exists(file_path):
                subprocess.run(['chown', f'{admin_user}:{admin_user}', file_path], 
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
        env = os.environ.copy()
        env['GIT_TERMINAL_PROMPT'] = '0'
        result = subprocess.run([
            "git", "clone", "--depth", "1", 
            "https://github.com/homeserversltd/documentation.git", temp_dir
        ], capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL, env=env)
        
        if result.returncode != 0:
            log_message(f"Git clone failed: {result.stderr}", "ERROR")
            return False
        
        # Deploy content from temp directory
        log_message("Deploying new documentation content...", "INFO")
        if not deploy_docs_content_from_temp(temp_dir):
            shutil.rmtree(temp_dir)
            return False
        
        # Save new version
        if not save_versions(get_current_mkdocs_version(), get_current_material_theme_version(), latest_docs_version):
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
        "theme_version": None,
        "service_active": False,
        "docs_version": None
    }
    try:
        verification["version"] = get_current_mkdocs_version()
        verification["theme_version"] = get_current_material_theme_version()
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
    
    # Handle --check flag for status reporting
    if "--check" in args:
        return check(module_dir)
    
    log_message("Starting mkdocs update...")
    
    # Check what updates are needed using the new version checking logic
    mkdocs_update_needed, theme_update_needed, docs_update_needed, version_info = _check_version_update_needed()
    
    # If no updates needed, just return
    if not any([mkdocs_update_needed, theme_update_needed, docs_update_needed]):
        log_message("All components are up to date, no updates needed")
        return {"success": True, "updated": False}
    
    # Backup current state if any component needs updating
    state_manager = StateManager()
    files_to_backup = get_mkdocs_paths() + [DOCS_LOCAL_PATH, DOCS_VERSION_FILE]
    
    backup_name = f"pre_update_mkdocs_{version_info['local']['mkdocs']}_to_{version_info['remote']['mkdocs']}_theme_{version_info['local']['theme']}_to_{version_info['remote']['theme']}_docs_{version_info['local']['docs']}_to_{version_info['remote']['docs']}"
    
    backup_success = state_manager.backup_module_state(
        "mkdocs",
        backup_name,
        files=files_to_backup
    )
    if not backup_success:
        return {"success": False, "error": "Backup failed"}
    
    try:
        # Stop service before updates
        systemctl("stop")
        
        # Update MkDocs software if needed
        if mkdocs_update_needed:
            current_mkdocs = version_info['local']['mkdocs']
            latest_mkdocs = version_info['remote']['mkdocs']
            log_message(f"Updating MkDocs software from {current_mkdocs} to {latest_mkdocs}", "INFO")
            subprocess.run(["/opt/docs/venv/bin/pip", "install", "--upgrade", "mkdocs"], check=True)
        
        # Update Material theme if needed
        if theme_update_needed:
            current_theme = version_info['local']['theme']
            latest_theme = version_info['remote']['theme']
            log_message(f"Updating Material theme from {current_theme} to {latest_theme}", "INFO")
            subprocess.run(["/opt/docs/venv/bin/pip", "install", "--upgrade", "mkdocs-material"], check=True)
        
        # Update documentation if needed
        if docs_update_needed:
            if not update_documentation():
                raise Exception("Documentation update failed")
        
        # Restore permissions
        restore_mkdocs_permissions()
        
        # Start service
        systemctl("start")
        time.sleep(5)  # Wait for startup
        
        # Verify everything is working
        verification = verify_mkdocs_installation()
        new_mkdocs_version = verification.get("version")
        new_docs_version = verification.get("docs_version")
        
        # Get new theme version after update
        new_theme_version = get_current_material_theme_version()
        
        # Update local version tracking
        save_versions(new_mkdocs_version, new_theme_version, new_docs_version)
        
        success_conditions = [
            # For software updates: either no update needed, or software is working
            not mkdocs_update_needed or (new_mkdocs_version is not None and verification["pip_installed"]),
            # For theme updates: either no update needed, or theme version matches
            not theme_update_needed or (new_theme_version is not None and new_theme_version == version_info['remote']['theme']),
            # For docs updates: either no update needed, or docs version matches
            not docs_update_needed or (new_docs_version is not None and new_docs_version == version_info['remote']['docs']),
            # Service must be active
            verification["service_active"]
        ]
        
        if all(success_conditions):
            log_message("MkDocs update completed successfully", "INFO")
            return {
                "success": True, 
                "updated": True, 
                "verification": verification,
                "software_updated": mkdocs_update_needed,
                "theme_updated": theme_update_needed,
                "docs_updated": docs_update_needed,
                "version_info": version_info
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