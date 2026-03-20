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
from pathlib import Path
from typing import Dict, Any, Optional, List
import urllib.request
import tempfile
from updates.index import log_message
from updates.utils.state_manager import StateManager
from updates.utils.permissions import restore_service_permissions_simple, PermissionManager, PermissionTarget
from updates.utils.moduleUtils import conditional_config_return

# Load module configuration from index.json
def load_module_config():
    """
    Load configuration from the module's index.json file.
    Returns:
        dict: Configuration data or default values if loading fails
    """
    try:
        config_path = os.path.join(os.path.dirname(__file__), "index.json")
        with open(config_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        log_message(f"Failed to load module config: {e}", "WARNING")
        # Return default configuration
        return {
            "metadata": {
                "schema_version": "1.0.0",
                "module_name": "gogs"
            },
            "config": {
                "directories": {
                    "data_dir": "/var/lib/gogs",
                    "config_dir": "/etc/gogs",
                    "install_dir": "/opt/gogs",
                    "config_file": "/opt/gogs/custom/conf/app.ini",
                    "repo_path": "/mnt/nas/git/repositories",
                    "gogs_bin": "/opt/gogs/gogs"
                },
                "installation": {
                    "github_api_url": "https://api.github.com/repos/gogs/gogs/releases/latest",
                    "download_url_template": "https://dl.gogs.io/{version}/gogs_{version}_linux_amd64.tar.gz",
                    "extract_path": "/opt/"
                },
                "permissions": {
                    "owner": "git",
                    "group": "git",
                    "mode": "750"
                }
            }
        }

# Global configuration
MODULE_CONFIG = load_module_config()

def get_gogs_paths():
    """
    Get all Gogs-related paths that should be backed up.
    Returns:
        list: List of paths that exist and should be backed up
    """
    paths = []
    config = MODULE_CONFIG["config"]
    
    # Add all configured directories
    for key, dir_config in config["directories"].items():
        # Handle both new format (dict with path) and legacy format (string)
        path = dir_config["path"] if isinstance(dir_config, dict) else dir_config
        
        if os.path.exists(path):
            paths.append(path)
            log_message(f"Found Gogs path for backup: {path}")
        else:
            log_message(f"Gogs path not found (skipping): {path}", "DEBUG")
    
    return paths

def detect_git_server() -> str:
    """
    Detect which git server is present on the system: Gogs, Forgejo, or none.
    Used to skip Gogs-specific logic when the box has been migrated to Forgejo.
    Returns: "forgejo" | "gogs" | "none"
    """
    try:
        # Prefer service state (most reliable); fallback to binary presence
        for unit, kind in [("forgejo", "forgejo"), ("gogs", "gogs")]:
            r = subprocess.run(
                ["systemctl", "is-active", "--quiet", unit],
                capture_output=True,
                timeout=5,
            )
            if r.returncode == 0:
                return kind
        # Binary fallback (e.g. systemd not available or unit name differs)
        if os.path.isfile("/opt/forgejo/forgejo") and os.access("/opt/forgejo/forgejo", os.X_OK):
            return "forgejo"
        gogs_bin_config = MODULE_CONFIG["config"]["directories"].get("gogs_bin")
        if gogs_bin_config:
            bin_path = gogs_bin_config["path"] if isinstance(gogs_bin_config, dict) else gogs_bin_config
            if os.path.isfile(bin_path) and os.access(bin_path, os.X_OK):
                return "gogs"
        return "none"
    except Exception as e:
        log_message(f"detect_git_server: {e}", "WARNING")
        return "none"


def get_gogs_version():
    """Detect currently installed Gogs version."""
    try:
        gogs_bin_config = MODULE_CONFIG["config"]["directories"]["gogs_bin"]
        bin_path = gogs_bin_config["path"] if isinstance(gogs_bin_config, dict) else gogs_bin_config
        if not os.path.isfile(bin_path) or not os.access(bin_path, os.X_OK):
            return None
        
        result = subprocess.run([bin_path, "--version"], capture_output=True, text=True, check=False)
        if result.returncode == 0:
            # Output format: "Gogs version X.Y.Z"
            version_parts = result.stdout.strip().split()
            if len(version_parts) >= 3 and version_parts[1] == "version":
                return version_parts[2]
        return None
    except Exception as e:
        log_message(f"Warning: Failed to detect Gogs version: {e}")
        return None

def get_latest_gogs_version():
    """
    Get the latest Gogs version from GitHub releases.
    Returns:
        str: Latest version string or None
    """
    try:
        api_url = MODULE_CONFIG["config"]["installation"]["github_api_url"]
        with urllib.request.urlopen(api_url) as resp:
            data = json.load(resp)
            tag = data.get("tag_name", "")
            if tag.startswith("v"):
                return tag[1:]
            return tag
    except Exception as e:
        log_message(f"Failed to get latest version info: {e}", "ERROR")
        return None


def _http_head_ok(url: str, timeout: int = 30) -> bool:
    """Return True if URL responds with 2xx/3xx to HEAD (used when GitHub API is unavailable)."""
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = getattr(resp, "status", 200)
            return 200 <= int(code) < 400
    except Exception:
        return False


def resolve_gogs_linux_amd64_tarball_url(version: str) -> Optional[str]:
    """
    Resolve the linux/amd64 .tar.gz download URL for a Gogs release.

    Upstream changed naming between 0.13.x and 0.14.x:
    - 0.13.3: gogs_0.13.3_linux_amd64.tar.gz
    - 0.14.2: gogs_v0.14.2_linux_amd64.tar.gz

    A single string template cannot cover both; we prefer the GitHub release assets list.
    """
    ver_plain = version[1:] if version.startswith("v") else version
    tag_with_v = f"v{ver_plain}"
    api_url = f"https://api.github.com/repos/gogs/gogs/releases/tags/{tag_with_v}"
    try:
        req = urllib.request.Request(
            api_url,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "homeserver-updates-gogs"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.load(resp)
        for asset in data.get("assets", []):
            name = asset.get("name") or ""
            if "linux_amd64" in name and name.endswith(".tar.gz"):
                url = asset.get("browser_download_url")
                if url:
                    log_message(f"Resolved Gogs tarball from release assets: {name}")
                    return url
        log_message(f"No linux_amd64 .tar.gz asset in GitHub release {tag_with_v}", "WARNING")
    except Exception as e:
        log_message(f"GitHub API tarball resolution failed ({api_url}): {e}", "WARNING")

    base = f"https://github.com/gogs/gogs/releases/download/{tag_with_v}"
    for name in (f"gogs_{ver_plain}_linux_amd64.tar.gz", f"gogs_{tag_with_v}_linux_amd64.tar.gz"):
        candidate = f"{base}/{name}"
        if _http_head_ok(candidate):
            log_message(f"Resolved Gogs tarball via URL probe: {candidate}")
            return candidate
    return None


def validate_critical_data(install_dir):
    """
    Ensure critical user data exists before update to prevent data loss.
    Args:
        install_dir: Path to Gogs installation directory
    Returns:
        dict: Validation results with status and details
    """
    validation_results = {
        "has_repositories": False,
        "has_custom_config": False,
        "has_data_dir": False,
        "repositories_count": 0,
        "critical_paths": {},
        "warnings": []
    }
    
    try:
        # Check for repositories directory
        repo_path = os.path.join(install_dir, "repositories")
        validation_results["critical_paths"]["repositories"] = repo_path
        
        if os.path.exists(repo_path):
            validation_results["has_repositories"] = True
            # Count repositories (directories at root level)
            try:
                repo_count = len([d for d in os.listdir(repo_path) 
                                if os.path.isdir(os.path.join(repo_path, d))])
                validation_results["repositories_count"] = repo_count
                if repo_count > 0:
                    log_message(f"Found {repo_count} repositories to preserve")
                else:
                    validation_results["warnings"].append("Repositories directory exists but is empty")
            except OSError as e:
                validation_results["warnings"].append(f"Cannot read repositories directory: {e}")
        else:
            validation_results["warnings"].append("Repositories directory not found - no repos to preserve")
        
        # Check for custom configuration
        config_path = os.path.join(install_dir, "custom", "conf", "app.ini")
        validation_results["critical_paths"]["config"] = config_path
        
        if os.path.exists(config_path):
            validation_results["has_custom_config"] = True
            log_message("Found custom configuration to preserve")
        else:
            validation_results["warnings"].append("Custom configuration not found - will use defaults")
        
        # Check for data directory
        data_path = os.path.join(install_dir, "data")
        validation_results["critical_paths"]["data"] = data_path
        
        if os.path.exists(data_path):
            validation_results["has_data_dir"] = True
            log_message("Found data directory to preserve")
        else:
            validation_results["warnings"].append("Data directory not found - will be created")
        
        # Log validation results
        log_message("Pre-update validation completed:")
        log_message(f"  Repositories: {'✓' if validation_results['has_repositories'] else '✗'} ({validation_results['repositories_count']} repos)")
        log_message(f"  Custom config: {'✓' if validation_results['has_custom_config'] else '✗'}")
        log_message(f"  Data directory: {'✓' if validation_results['has_data_dir'] else '✗'}")
        
        if validation_results["warnings"]:
            for warning in validation_results["warnings"]:
                log_message(f"  WARNING: {warning}", "WARNING")
        
        return validation_results
        
    except Exception as e:
        log_message(f"Error during pre-update validation: {e}", "ERROR")
        validation_results["error"] = str(e)
        return validation_results

def verify_gogs_installation():
    """
    Verify that Gogs is properly installed and functional.
    Returns:
        dict: Verification results with status and details
    """
    verification_results = {
        "binary_exists": False,
        "binary_executable": False,
        "version_readable": False,
        "config_dir_exists": False,
        "data_dir_exists": False,
        "install_dir_exists": False,
        "version": None,
        "paths": {}
    }
    
    try:
        # Check binary
        gogs_bin_config = MODULE_CONFIG["config"]["directories"]["gogs_bin"]
        bin_path = gogs_bin_config["path"] if isinstance(gogs_bin_config, dict) else gogs_bin_config
        verification_results["paths"]["binary"] = bin_path
        
        if os.path.exists(bin_path):
            verification_results["binary_exists"] = True
            if os.access(bin_path, os.X_OK):
                verification_results["binary_executable"] = True
                
                # Check version
                version = get_gogs_version()
                if version:
                    verification_results["version_readable"] = True
                    verification_results["version"] = version
        
        # Check directories
        for dir_key, dir_config in MODULE_CONFIG["config"]["directories"].items():
            dir_path = dir_config["path"] if isinstance(dir_config, dict) else dir_config
            verification_results[f"{dir_key}_exists"] = os.path.exists(dir_path)
            verification_results["paths"][dir_key] = dir_path
        
        # Log verification results
        for check, result in verification_results.items():
            if check not in ["version", "paths"]:
                status = "✓" if result else "✗"
                log_message(f"Gogs verification - {check}: {status}")
        
        if verification_results["version"]:
            log_message(f"Gogs verification - version: {verification_results['version']}")
        
    except Exception as e:
        log_message(f"Error during Gogs verification: {e}", "ERROR")
    
    return verification_results

def preserve_user_data(install_dir, temp_backup_dir):
    """
    Backup critical user data before update to prevent data loss.
    Args:
        install_dir: Path to current Gogs installation
        temp_backup_dir: Temporary directory to store user data backup
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        log_message("Preserving user data before update...")
        
        # Directories to preserve (user data)
        preserve_directories = ["repositories", "custom", "data", "log"]
        
        for dir_name in preserve_directories:
            source_path = os.path.join(install_dir, dir_name)
            backup_path = os.path.join(temp_backup_dir, dir_name)
            
            if os.path.exists(source_path):
                log_message(f"Preserving {dir_name} directory...")
                if os.path.isdir(source_path):
                    shutil.copytree(source_path, backup_path, dirs_exist_ok=True)
                else:
                    shutil.copy2(source_path, backup_path)
                log_message(f"✓ Preserved {dir_name}")
            else:
                log_message(f"Directory {dir_name} not found - skipping", "DEBUG")
        
        log_message("User data preservation completed successfully")
        return True
        
    except Exception as e:
        log_message(f"Failed to preserve user data: {e}", "ERROR")
        return False

def replace_binary_only(install_dir, new_gogs_dir):
    """
    Replace only the Gogs binary and static files, preserving user data.
    Args:
        install_dir: Path to current Gogs installation
        new_gogs_dir: Path to new Gogs installation from download
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        log_message("Replacing binary and static files...")
        
        # Files to replace (binary and static content)
        replace_files = ["gogs", "LICENSE", "README.md", "README_ZH.md", "scripts"]
        
        for item_name in replace_files:
            source_path = os.path.join(new_gogs_dir, item_name)
            target_path = os.path.join(install_dir, item_name)
            
            if os.path.exists(source_path):
                if os.path.isdir(source_path):
                    # Remove existing directory and replace
                    if os.path.exists(target_path):
                        shutil.rmtree(target_path)
                    shutil.copytree(source_path, target_path)
                else:
                    # Copy file
                    shutil.copy2(source_path, target_path)
                log_message(f"✓ Replaced {item_name}")
            else:
                log_message(f"Item {item_name} not found in new installation", "WARNING")
        
        log_message("Binary replacement completed successfully")
        return True
        
    except Exception as e:
        log_message(f"Failed to replace binary files: {e}", "ERROR")
        return False

def restore_user_data(install_dir, temp_backup_dir):
    """
    Restore user data after binary update.
    Args:
        install_dir: Path to Gogs installation directory
        temp_backup_dir: Temporary directory containing user data backup
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        log_message("Restoring user data after update...")
        
        # Restore each preserved directory
        for item_name in os.listdir(temp_backup_dir):
            backup_path = os.path.join(temp_backup_dir, item_name)
            target_path = os.path.join(install_dir, item_name)
            
            if os.path.isdir(backup_path):
                # Remove existing directory and restore
                if os.path.exists(target_path):
                    shutil.rmtree(target_path)
                shutil.copytree(backup_path, target_path)
            else:
                # Copy file
                shutil.copy2(backup_path, target_path)
            
            log_message(f"✓ Restored {item_name}")
        
        log_message("User data restoration completed successfully")
        return True
        
    except Exception as e:
        log_message(f"Failed to restore user data: {e}", "ERROR")
        return False

def validate_preservation(install_dir, validation_before):
    """
    Validate that user data was preserved correctly after update.
    Args:
        install_dir: Path to Gogs installation directory
        validation_before: Validation results from before update
    Returns:
        dict: Post-update validation results
    """
    try:
        log_message("Validating data preservation after update...")
        
        validation_after = {
            "repositories_preserved": False,
            "config_preserved": False,
            "data_preserved": False,
            "repositories_count_after": 0,
            "preservation_success": False
        }
        
        # Check repositories
        repo_path = os.path.join(install_dir, "repositories")
        if os.path.exists(repo_path):
            validation_after["repositories_preserved"] = True
            try:
                repo_count = len([d for d in os.listdir(repo_path) 
                                if os.path.isdir(os.path.join(repo_path, d))])
                validation_after["repositories_count_after"] = repo_count
                
                if validation_before.get("repositories_count", 0) == repo_count:
                    log_message(f"✓ Repositories preserved: {repo_count} repos")
                else:
                    log_message(f"⚠ Repository count changed: {validation_before.get('repositories_count', 0)} → {repo_count}", "WARNING")
            except OSError as e:
                log_message(f"⚠ Cannot verify repository count: {e}", "WARNING")
        else:
            log_message("✗ Repositories directory missing after update", "ERROR")
        
        # Check custom config
        config_path = os.path.join(install_dir, "custom", "conf", "app.ini")
        if os.path.exists(config_path):
            validation_after["config_preserved"] = True
            log_message("✓ Custom configuration preserved")
        else:
            log_message("✗ Custom configuration missing after update", "ERROR")
        
        # Check data directory
        data_path = os.path.join(install_dir, "data")
        if os.path.exists(data_path):
            validation_after["data_preserved"] = True
            log_message("✓ Data directory preserved")
        else:
            log_message("✗ Data directory missing after update", "ERROR")
        
        # Overall preservation success
        validation_after["preservation_success"] = all([
            validation_after["repositories_preserved"],
            validation_after["config_preserved"],
            validation_after["data_preserved"]
        ])
        
        if validation_after["preservation_success"]:
            log_message("✓ Data preservation validation passed")
        else:
            log_message("✗ Data preservation validation failed", "ERROR")
        
        return validation_after
        
    except Exception as e:
        log_message(f"Error during preservation validation: {e}", "ERROR")
        return {"preservation_success": False, "error": str(e)}


def _data_preserving_install_from_new_gogs_tree(install_dir: str, new_gogs_dir: str) -> Dict[str, Any]:
    """
    Replace packaged files under install_dir while preserving repositories/custom/data/log.
    new_gogs_dir must match release layout (contains executable 'gogs', scripts/, etc.).
    """
    log_message("Performing pre-update validation...")
    validation_before = validate_critical_data(install_dir)
    temp_backup_dir = tempfile.mkdtemp(prefix="gogs_user_data_")
    try:
        if not preserve_user_data(install_dir, temp_backup_dir):
            raise Exception("Failed to preserve user data")
        if not replace_binary_only(install_dir, new_gogs_dir):
            raise Exception("Failed to replace binary files")
        if not restore_user_data(install_dir, temp_backup_dir):
            raise Exception("Failed to restore user data")
        log_message("Performing post-update validation...")
        validation_after = validate_preservation(install_dir, validation_before)
        shutil.rmtree(temp_backup_dir)
        result = {
            "success": True,
            "validation_before": validation_before,
            "validation_after": validation_after,
            "preservation_success": validation_after.get("preservation_success", False),
        }
        if result["preservation_success"]:
            log_message("✓ Data-preserving installation completed successfully")
        else:
            log_message("⚠ Installation completed but data preservation had issues", "WARNING")
        return result
    except Exception as e:
        if os.path.exists(temp_backup_dir):
            shutil.rmtree(temp_backup_dir)
        log_message(f"Data-preserving install from tree failed: {e}", "ERROR")
        return {
            "success": False,
            "error": str(e),
            "preservation_success": False,
        }


def install_gogs_binary(version):
    """
    Install Gogs from pre-compiled binary while preserving user data.
    Args:
        version: Version to install
    Returns:
        dict: Installation results with success status and validation data
    """
    install_dir_config = MODULE_CONFIG["config"]["directories"]["install_dir"]
    install_dir = install_dir_config["path"] if isinstance(install_dir_config, dict) else install_dir_config

    download_url = resolve_gogs_linux_amd64_tarball_url(version)
    if not download_url:
        tpl = MODULE_CONFIG["config"]["installation"].get("binary_download_url_template")
        if tpl:
            try:
                download_url = tpl.format(version=version)
                log_message("Using binary_download_url_template as last resort (may 404 on some releases)")
            except Exception as e:
                log_message(f"Could not format binary_download_url_template: {e}", "WARNING")

    if not download_url:
        log_message("Could not resolve any linux_amd64 tarball URL for Gogs", "ERROR")
        return {"success": False, "error": "No download URL", "preservation_success": False}

    log_message(f"Attempting data-preserving binary installation from {download_url}")
    temp_extract = tempfile.mkdtemp(prefix="gogs_new_")
    temp_archive: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as temp_file:
            temp_archive = temp_file.name
        log_message(f"Downloading {download_url}...")
        urllib.request.urlretrieve(download_url, temp_archive)
        subprocess.run(["tar", "xzf", temp_archive, "-C", temp_extract], check=True)
        os.unlink(temp_archive)
        temp_archive = None

        new_gogs_dir = os.path.join(temp_extract, "gogs")
        if not os.path.isdir(new_gogs_dir):
            raise Exception(f"Unexpected archive layout: missing {new_gogs_dir}")

        result = _data_preserving_install_from_new_gogs_tree(install_dir, new_gogs_dir)
        return result
    except Exception as e:
        log_message(f"Data-preserving binary installation failed: {e}", "ERROR")
        return {
            "success": False,
            "error": str(e),
            "preservation_success": False,
        }
    finally:
        if temp_archive and os.path.exists(temp_archive):
            try:
                os.unlink(temp_archive)
            except OSError:
                pass
        if os.path.exists(temp_extract):
            shutil.rmtree(temp_extract)


def install_gogs_from_source(version) -> Optional[Dict[str, Any]]:
    """
    Fallback: build with go and apply the same data-preserving swap as the binary path.
    Requires a Go toolchain compatible with Gogs' go.mod (see upstream); no Makefile.
    Returns the same result dict shape as install_gogs_binary on success, else None.
    """
    repo_url = MODULE_CONFIG["config"]["installation"]["source_repo_url"]
    build_dir = "/tmp/gogs_build"
    build_timeout = 900

    install_dir_config = MODULE_CONFIG["config"]["directories"]["install_dir"]
    install_dir = install_dir_config["path"] if isinstance(install_dir_config, dict) else install_dir_config

    log_message(f"Attempting source build for version {version}")
    if os.path.exists(build_dir):
        shutil.rmtree(build_dir)

    tag = f"v{version}" if not str(version).startswith("v") else str(version)
    try:
        log_message(f"Cloning repository {repo_url} (ref {tag})")
        subprocess.run(
            ["git", "clone", "--depth", "1", "--branch", tag, repo_url, build_dir],
            check=True,
            timeout=300,
        )
        go_version_result = subprocess.run(
            ["go", "version"], capture_output=True, text=True, check=True
        )
        log_message(f"Using {go_version_result.stdout.strip()}")
        log_message("Building Gogs from source (go build)...")
        subprocess.run(
            ["go", "build", "-v", "-trimpath", "-o", "gogs", "."],
            cwd=build_dir,
            check=True,
            timeout=build_timeout,
        )
        built_binary = os.path.join(build_dir, "gogs")
        if not os.path.isfile(built_binary):
            log_message("go build finished but gogs binary missing", "ERROR")
            return None
        log_message("Applying data-preserving install from source checkout...")
        res = _data_preserving_install_from_new_gogs_tree(install_dir, build_dir)
        if not res.get("success", False):
            log_message(f"Install after build failed: {res.get('error')}", "ERROR")
            return None
        return res
    except subprocess.TimeoutExpired:
        log_message("Source build timed out", "ERROR")
        return None
    except Exception as e:
        log_message(f"Source build failed: {e}", "WARNING")
        return None
    finally:
        if os.path.exists(build_dir):
            shutil.rmtree(build_dir)

def restore_gogs_permissions():
    """
    Restore proper ownership and permissions for Gogs files and directories.
    This is critical after updates that run as root to prevent service failures.
    
    Returns:
        bool: True if permissions were restored successfully, False otherwise
    """
    try:
        log_message("Restoring Gogs permissions after update...")
        
        config = MODULE_CONFIG["config"]
        permission_manager = PermissionManager("gogs")
        
        # Build permission targets from JSON configuration
        targets = []
        default_owner = config["permissions"]["owner"]
        default_group = config["permissions"]["group"]
        
        for dir_key, dir_config in config["directories"].items():
            if isinstance(dir_config, dict):
                # New format with embedded permissions
                path = dir_config["path"]
                owner = dir_config.get("owner", default_owner)
                mode = int(dir_config["mode"], 8)  # Convert string to octal
                
                # Determine if it's a directory or file and if recursive
                is_directory = os.path.isdir(path) if os.path.exists(path) else "dir" in dir_key
                recursive = is_directory and dir_key in ["install_dir", "repo_path", "data_dir", "config_dir"]
                
                targets.append(PermissionTarget(
                    path=path,
                    owner=owner,
                    group=default_group,
                    mode=mode,
                    recursive=recursive
                ))
            else:
                # Legacy format fallback
                targets.append(PermissionTarget(
                    path=dir_config,
                    owner=default_owner,
                    group=default_group,
                    mode=0o755,
                    recursive=True
                ))
        
        success = permission_manager.set_permissions(targets)
        
        if success:
            log_message("Successfully restored Gogs permissions")
        else:
            log_message("Failed to restore some Gogs permissions", "WARNING")
            
        return success
        
    except Exception as e:
        log_message(f"Critical error during Gogs permission restoration: {e}", "ERROR")
        return False

def main(args=None):
    """
    Main entry point for Gogs update module.
    Detects Gogs vs Forgejo vs none; skips Gogs-specific logic when Forgejo is present (post-migration).
    Args:
        args: List of arguments (supports '--version', '--check', '--verify', '--config')
    Returns:
        dict: Status and results of the update
    """
    if args is None:
        args = []
    
    # Module directory for reference
    module_dir = Path(__file__).parent
    
    # Detect which git server is present so we don't run Gogs logic on Forgejo-migrated boxes
    git_server = detect_git_server()
    if git_server == "forgejo":
        log_message("Git server is Forgejo (migrated); skipping Gogs module")
        return {"success": True, "skipped": True, "reason": "forgejo"}
    if git_server == "none":
        log_message("No Gogs or Forgejo detected; skipping Gogs module")
        return {"success": True, "skipped": True, "reason": "none"}
    # From here: git_server == "gogs"

    # Handle command line arguments first
    if args and len(args) > 0:
        if args[0] == "--version":
            version = get_gogs_version()
            if version:
                log_message(f"Detected Gogs version: {version}")
                return {"success": True, "version": version}
            else:
                log_message("Could not detect Gogs version")
                return {"success": False, "error": "Version detection failed"}
        elif args[0] == "--fix-permissions":
            log_message("Manually restoring Gogs permissions...")
            if restore_gogs_permissions():
                log_message("✓ Permissions restored successfully")
                return {"success": True, "message": "Permissions restored"}
            else:
                log_message("✗ Failed to restore permissions")
                return {"success": False, "error": "Permission restoration failed"}
    
    log_message("Starting Gogs module update...")
    
    SERVICE_NAME = MODULE_CONFIG["metadata"]["module_name"]
    
    # --config mode: show current configuration
    if len(args) > 0 and args[0] == "--config":
        log_message("Current Gogs module configuration:")
        for key, dir_config in MODULE_CONFIG["config"]["directories"].items():
            path = dir_config["path"] if isinstance(dir_config, dict) else dir_config
            log_message(f"  {key}: {path}")
        
        return {
            "success": True,
            "config": MODULE_CONFIG,
            "paths": {k: (v["path"] if isinstance(v, dict) else v) for k, v in MODULE_CONFIG["config"]["directories"].items()},
            "git_server": git_server,
        }

    # --verify mode: comprehensive installation verification
    if len(args) > 0 and args[0] == "--verify":
        log_message("Running comprehensive Gogs verification...")
        verification = verify_gogs_installation()
        
        all_checks_passed = all([
            verification["binary_exists"],
            verification["binary_executable"], 
            verification["version_readable"]
        ])
        
        result = {
            "success": all_checks_passed,
            "verification": verification,
            "version": verification.get("version")
        }
        
        # Include config only in debug mode
        result = conditional_config_return(result, MODULE_CONFIG)
        
        return result

    # --check mode: simple version check
    if len(args) > 0 and args[0] == "--check":
        version = get_gogs_version()
        if version:
            log_message(f"OK - Current version: {version}")
            return {"success": True, "version": version}
        else:
            log_message("Gogs binary not found", "ERROR")
            return {"success": False, "error": "Not found"}

    # Get current version
    current_version = get_gogs_version()
    if not current_version:
        log_message("Failed to get current version of Gogs", "ERROR")
        return {"success": False, "error": "No current version"}
    log_message(f"Current Gogs version: {current_version}")

    # Get latest version
    latest_version = get_latest_gogs_version()
    if not latest_version:
        log_message("Failed to get latest version information", "ERROR")
        return {"success": False, "error": "No latest version"}
    log_message(f"Latest available version: {latest_version}")

    # Compare and update if needed
    if current_version != latest_version:
        log_message("Update available. Creating comprehensive backup...")
        
        # Initialize state manager
        state_manager = StateManager()
        
        # Get all Gogs-related paths for comprehensive backup
        files_to_backup = get_gogs_paths()
        
        if not files_to_backup:
            log_message("No Gogs files found for backup", "WARNING")
            return {"success": False, "error": "No files to backup"}
        
        log_message(f"Creating backup for {len(files_to_backup)} Gogs paths...")
        
        # Create backup using the simplified API
        backup_success = state_manager.backup_module_state(
            module_name=SERVICE_NAME,
            description=f"pre_update_{current_version}_to_{latest_version}",
            files=files_to_backup
        )
        
        if not backup_success:
            log_message("Failed to create backup", "ERROR")
            return {"success": False, "error": "Backup failed"}
        
        log_message("Backup created successfully")
        
        # Perform the update
        log_message("Installing update...")
        try:
            # Try data-preserving binary installation first
            install_result = install_gogs_binary(latest_version)
            
            # Check if installation was successful
            if not install_result.get("success", False):
                # If binary installation fails and fallback is enabled, try source build
                if MODULE_CONFIG["config"]["installation"].get("fallback_to_source", False):
                    log_message("Binary installation failed, attempting source build...")
                    source_result = install_gogs_from_source(latest_version)
                    if not source_result or not source_result.get("success", False):
                        raise Exception("Both binary and source installation methods failed")
                    install_result = source_result
                else:
                    raise Exception(f"Binary installation failed: {install_result.get('error', 'Unknown error')}")
            else:
                # Binary installation succeeded, check data preservation
                if not install_result.get("preservation_success", False):
                    log_message("⚠ Update completed but data preservation had issues", "WARNING")
                    log_message("Check validation results for details")
                else:
                    log_message("✓ Update completed with full data preservation")
            
            # Restore permissions using the centralized permission system
            restore_gogs_permissions()
            
            # Verify new installation
            log_message("Verifying new installation...")
            verification = verify_gogs_installation()
            new_version = verification.get("version")
            
            if new_version == latest_version:
                log_message(f"Successfully updated Gogs from {current_version} to {new_version}")
                
                # Run post-update verification
                if not verification["binary_executable"] or not verification["version_readable"]:
                    raise Exception("Post-update verification failed - installation appears incomplete")
                
                # Include data preservation results in final result
                result = {
                    "success": True, 
                    "updated": True, 
                    "old_version": current_version, 
                    "new_version": new_version,
                    "verification": verification,
                    "data_preservation": install_result.get("validation_after", {}),
                    "preservation_success": install_result.get("preservation_success", False)
                }
                
                # Include config only in debug mode
                result = conditional_config_return(result, MODULE_CONFIG)
                
                return result
            else:
                raise Exception(f"Version mismatch after update. Expected: {latest_version}, Got: {new_version}")
                
        except Exception as e:
            log_message(f"Update failed: {e}", "ERROR")
            log_message("Restoring from backup...")
            
            # Restore using simplified API
            rollback_success = state_manager.restore_module_state(SERVICE_NAME)
            
            if rollback_success:
                log_message("Successfully restored from backup")
                # Verify rollback worked
                restored_version = get_gogs_version()
                log_message(f"Restored version: {restored_version}")
            else:
                log_message("Failed to restore from backup", "ERROR")
            
            result = {
                "success": False, 
                "error": str(e),
                "rollback_success": rollback_success,
                "restored_version": get_gogs_version() if rollback_success else None
            }
            
            # Include config only in debug mode
            result = conditional_config_return(result, MODULE_CONFIG)
            
            return result
    else:
        log_message(f"Gogs is already at the latest version ({current_version})")
        
        # Skip verification when no update is needed - it's not necessary
        # Verification is only useful when we've made changes or need to diagnose issues
        log_message("Skipping verification - no update needed")
        
        result = {
            "success": True, 
            "updated": False, 
            "version": current_version,
            "verification": None  # No verification performed when not needed
        }
        
        # Include config only in debug mode
        result = conditional_config_return(result, MODULE_CONFIG)
        
        return result

if __name__ == "__main__":
    main()
