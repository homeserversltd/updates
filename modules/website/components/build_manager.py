"""
HOMESERVER Website Update Components
Copyright (C) 2024 HOMESERVER LLC

Build Manager Component

Handles all build and service management operations for the website update system including:
- NPM package installation and building
- Service stop/start/restart operations
- Build validation and cleanup
- Service health checks
"""

import os
import subprocess
import time
from typing import Dict, Any, List
from updates.index import log_message


class BuildManager:
    """Handles build and service management for website updates."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.base_dir = config.get('config', {}).get('target_paths', {}).get('base_directory', '/var/www/homeserver')
        
    def run_build_process(self) -> bool:
        """
        Run the complete build process including NPM install, build, and service restart.
        
        Returns:
            bool: True if build completed successfully, False otherwise
        """
        log_message("[BUILD] Starting build process...")
        
        try:
            # Step 1: Stop services
            if not self._stop_services():
                return False
            
            # Step 2: Install NPM dependencies
            if not self._npm_install():
                return False
            
            # Step 3: Build the frontend
            if not self._npm_build():
                return False
            
            # Step 4: Start services
            if not self._start_services():
                return False
            
            # Step 5: Validate services are running
            if not self._validate_services():
                return False
            
            log_message("[BUILD] ✓ Build process completed successfully")
            return True
            
        except Exception as e:
            log_message(f"[BUILD] ✗ Build process failed: {e}", "ERROR")
            return False
    
    def _stop_services(self) -> bool:
        """Stop relevant services before build."""
        services_to_stop = ['gunicorn.service']
        
        log_message("[BUILD] Stopping services...")
        
        for service in services_to_stop:
            try:
                log_message(f"[BUILD] Stopping {service}...")
                result = subprocess.run(
                    ['systemctl', 'stop', service],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if result.returncode == 0:
                    log_message(f"[BUILD] ✓ Stopped {service}")
                else:
                    log_message(f"[BUILD] ⚠ Failed to stop {service}: {result.stderr}", "WARNING")
                    # Continue anyway - service might not be running
                    
            except subprocess.TimeoutExpired:
                log_message(f"[BUILD] ⚠ Timeout stopping {service}", "WARNING")
            except Exception as e:
                log_message(f"[BUILD] ⚠ Error stopping {service}: {e}", "WARNING")
        
        # Give services time to stop
        time.sleep(2)
        log_message("[BUILD] ✓ Service stop phase completed")
        return True
    
    def _npm_install(self) -> bool:
        """Install NPM dependencies."""
        log_message("[BUILD] Installing NPM dependencies...")
        
        try:
            env = os.environ.copy()
            # Reduce npm verbosity
            env["NPM_CONFIG_LOGLEVEL"] = "error"
            env["LOGLEVEL"] = "error"
            result = subprocess.run(
                ['npm', 'install', '--silent', '--no-fund', '--no-audit'],
                cwd=self.base_dir,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
                env=env
            )
            
            if result.returncode != 0:
                log_message(f"[BUILD] ✗ NPM install failed: {result.stderr}", "ERROR")
                return False
            
            if result.stdout:
                # Log a summary, not the entire output
                lines = result.stdout.strip().split('\n')
                log_message(f"[BUILD] NPM install output ({len(lines)} lines):")
                for line in lines[-5:]:  # Show last 5 lines
                    log_message(f"[BUILD]   {line}")
            
            log_message("[BUILD] ✓ NPM dependencies installed successfully")
            return True
            
        except subprocess.TimeoutExpired:
            log_message("[BUILD] ✗ NPM install timed out", "ERROR")
            return False
        except Exception as e:
            log_message(f"[BUILD] ✗ NPM install failed: {e}", "ERROR")
            return False
    
    def _npm_build(self) -> bool:
        """Build the frontend application."""
        log_message("[BUILD] Building frontend application...")
        
        try:
            env = os.environ.copy()
            # Silence CRA eslint output during build and avoid CI treating warnings as errors
            env["DISABLE_ESLINT_PLUGIN"] = "true"
            env.setdefault("CI", "false")
            result = subprocess.run(
                ['npm', 'run', 'build', '--silent'],
                cwd=self.base_dir,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minute timeout for builds
                env=env
            )
            
            if result.returncode != 0:
                log_message(f"[BUILD] ✗ NPM build failed: {result.stderr}", "ERROR")
                return False
            
            if result.stdout:
                # Log a summary of the build
                lines = result.stdout.strip().split('\n')
                log_message(f"[BUILD] NPM build output ({len(lines)} lines):")
                for line in lines[-10:]:  # Show last 10 lines
                    log_message(f"[BUILD]   {line}")
            
            # Verify build output exists
            build_dir = os.path.join(self.base_dir, 'build')
            if not os.path.exists(build_dir):
                log_message(f"[BUILD] ✗ Build directory not found: {build_dir}", "ERROR")
                return False
            
            log_message("[BUILD] ✓ Frontend build completed successfully")
            return True
            
        except subprocess.TimeoutExpired:
            log_message("[BUILD] ✗ NPM build timed out", "ERROR")
            return False
        except Exception as e:
            log_message(f"[BUILD] ✗ NPM build failed: {e}", "ERROR")
            return False
    
    def _start_services(self) -> bool:
        """Start services after build."""
        services_to_start = ['gunicorn.service']
        
        log_message("[BUILD] Starting services...")
        
        for service in services_to_start:
            try:
                log_message(f"[BUILD] Starting {service}...")
                result = subprocess.run(
                    ['systemctl', 'start', service],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if result.returncode != 0:
                    log_message(f"[BUILD] ✗ Failed to start {service}: {result.stderr}", "ERROR")
                    return False
                
                log_message(f"[BUILD] ✓ Started {service}")
                
            except subprocess.TimeoutExpired:
                log_message(f"[BUILD] ✗ Timeout starting {service}", "ERROR")
                return False
            except Exception as e:
                log_message(f"[BUILD] ✗ Error starting {service}: {e}", "ERROR")
                return False
        
        # Give services time to start
        time.sleep(3)
        log_message("[BUILD] ✓ Service start phase completed")
        return True
    
    def _validate_services(self) -> bool:
        """Validate that services are running properly."""
        services_to_check = ['gunicorn.service']
        
        log_message("[BUILD] Validating services...")
        
        for service in services_to_check:
            try:
                # Check if service is active
                result = subprocess.run(
                    ['systemctl', 'is-active', service],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if result.stdout.strip() != 'active':
                    log_message(f"[BUILD] ✗ Service {service} is not active: {result.stdout.strip()}", "ERROR")
                    
                    # Get service status for debugging
                    status_result = subprocess.run(
                        ['systemctl', 'status', service, '--no-pager'],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    log_message(f"[BUILD] Service status: {status_result.stdout}", "ERROR")
                    return False
                
                log_message(f"[BUILD] ✓ Service {service} is active")
                
            except subprocess.TimeoutExpired:
                log_message(f"[BUILD] ✗ Timeout checking {service}", "ERROR")
                return False
            except Exception as e:
                log_message(f"[BUILD] ✗ Error checking {service}: {e}", "ERROR")
                return False
        
        log_message("[BUILD] ✓ All services validated successfully")
        return True
    
    def get_service_status(self) -> Dict[str, str]:
        """
        Get the current status of all relevant services.
        
        Returns:
            Dict[str, str]: Service name to status mapping
        """
        services = ['gunicorn.service']
        status = {}
        
        for service in services:
            try:
                result = subprocess.run(
                    ['systemctl', 'is-active', service],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                status[service] = result.stdout.strip()
            except Exception as e:
                status[service] = f"error: {e}"
        
        log_message(f"[BUILD] Service status: {status}")
        return status
    
    def cleanup_build_artifacts(self) -> bool:
        """
        Clean up build artifacts and temporary files.
        
        Returns:
            bool: True if cleanup successful, False otherwise
        """
        log_message("[BUILD] Cleaning up build artifacts...")
        
        cleanup_paths = [
            os.path.join(self.base_dir, 'node_modules/.cache'),
            os.path.join(self.base_dir, '.npm'),
            os.path.join(self.base_dir, 'npm-debug.log'),
            os.path.join(self.base_dir, 'yarn-error.log')
        ]
        
        cleaned_count = 0
        
        for path in cleanup_paths:
            try:
                if os.path.exists(path):
                    if os.path.isdir(path):
                        import shutil
                        shutil.rmtree(path)
                    else:
                        os.remove(path)
                    log_message(f"[BUILD] ✓ Cleaned: {path}")
                    cleaned_count += 1
            except Exception as e:
                log_message(f"[BUILD] ⚠ Failed to clean {path}: {e}", "WARNING")
        
        log_message(f"[BUILD] ✓ Cleanup completed ({cleaned_count} items cleaned)")
        return True
    
    def get_build_info(self) -> Dict[str, Any]:
        """
        Get information about the current build environment.
        
        Returns:
            Dict[str, Any]: Build environment information
        """
        info = {}
        
        try:
            # Node.js version
            result = subprocess.run(['node', '--version'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                info['node_version'] = result.stdout.strip()
        except:
            info['node_version'] = 'unknown'
        
        try:
            # NPM version
            result = subprocess.run(['npm', '--version'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                info['npm_version'] = result.stdout.strip()
        except:
            info['npm_version'] = 'unknown'
        
        # Check if package.json exists
        package_json_path = os.path.join(self.base_dir, 'package.json')
        info['package_json_exists'] = os.path.exists(package_json_path)
        
        # Check if build directory exists
        build_dir = os.path.join(self.base_dir, 'build')
        info['build_dir_exists'] = os.path.exists(build_dir)
        
        log_message(f"[BUILD] Build environment: {info}")
        return info
