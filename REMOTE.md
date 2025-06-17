# HOMESERVER Update Manager - Remote CLI Interface

## Overview

The HOMESERVER Update Manager provides a Python-based schema-driven update system orchestrated through a bash wrapper. This document details the precise CLI interface for remote integration, particularly for Flask backend services.

## System Architecture

```
updateManager.sh (Bash Wrapper)
    ↓
index.py (Python Orchestrator)
    ↓
modules/ (Individual Update Modules)
```

## CLI Interface

### Primary Command

```bash
/usr/local/lib/updates/updateManager.sh [OPTIONS]
```

### Available Options

#### Update Operations
| Option | Description | Use Case |
|--------|-------------|----------|
| `--check` | Check for updates without applying them | Status queries, pre-flight validation |
| `--legacy` | Use legacy manifest-based updates | Fallback mode, compatibility |
| `--help`, `-h` | Show usage information | Documentation, troubleshooting |
| *(default)* | Run schema-based updates | Normal update operations |

#### Module Management Operations
| Option | Arguments | Description | Use Case |
|--------|-----------|-------------|----------|
| `--enable <module>` | module name | Enable a module | Activate disabled functionality |
| `--disable <module>` | module name | Disable a module | Deactivate problematic modules |
| `--enable-component <module> <component>` | module, component | Enable specific component | Granular feature control |
| `--disable-component <module> <component>` | module, component | Disable specific component | Selective feature management |
| `--list-modules` | none | List all modules with status | System overview, inventory |
| `--status [module]` | optional module | Show module status/details | Detailed inspection |

## Flask Backend Integration

### Command Execution Patterns

#### 1. Update Status Check
```bash
# Non-destructive check for available updates
/usr/local/lib/updates/updateManager.sh --check
```

**Expected Behavior:**
- Exit code 0: Updates available or system current
- Exit code 1: System error or orchestrator unavailable
- Stdout: Timestamped log messages
- No system modifications

#### 2. Full Update Execution
```bash
# Execute schema-based updates (Git sync + module updates)
/usr/local/lib/updates/updateManager.sh
```

**Expected Behavior:**
- Git repository synchronization
- Module-specific update execution
- Configuration file updates
- Service restarts as needed

#### 3. Legacy Update Mode
```bash
# Fallback to manifest-based updates
/usr/local/lib/updates/updateManager.sh --legacy
```

**Expected Behavior:**
- Uses legacy update manifests
- Bypasses schema-driven system
- Compatibility with older update definitions

#### 4. Module Management Operations
```bash
# Enable/disable modules
/usr/local/lib/updates/updateManager.sh --enable website
/usr/local/lib/updates/updateManager.sh --disable adblock

# Enable/disable specific components
/usr/local/lib/updates/updateManager.sh --enable-component website frontend
/usr/local/lib/updates/updateManager.sh --disable-component website premium

# List and inspect modules
/usr/local/lib/updates/updateManager.sh --list-modules
/usr/local/lib/updates/updateManager.sh --status website
```

**Expected Behavior:**
- Immediate JSON configuration updates
- No service restarts or system changes
- Affects future update operations only
- Granular control over module components

## Process Management

### Execution Context
- **User:** Must run as root or with appropriate sudo privileges
- **Working Directory:** Script handles path resolution internally
- **Environment:** No special environment variables required

### Resource Requirements
- **CPU:** Low to moderate during Git operations
- **Memory:** Minimal (< 100MB typical)
- **Disk I/O:** Moderate during file operations
- **Network:** Required for Git synchronization

### Execution Time
- **Check Mode:** 5-15 seconds
- **Full Update:** 30 seconds to 5 minutes (depending on changes)
- **Legacy Mode:** Variable (depends on manifest complexity)
- **Module Management:** 1-3 seconds (JSON file operations only)

## Output Parsing

### Log Format
All output follows the pattern:
```
[YYYY-MM-DD HH:MM:SS] <message>
```

### Key Status Indicators

#### Success Patterns
```
[timestamp] ✓ Update system completed successfully
[timestamp] ✓ Module management operation completed successfully
[timestamp] ✓ Module '<name>' enabled
[timestamp] ✓ Component '<component>' enabled in module '<module>'
```

#### Error Patterns
```
[timestamp] ✗ Update system failed with exit code <code>
[timestamp] ✗ Module management operation failed with exit code <code>
[timestamp] Error: Python orchestrator not found at <path>
[timestamp] Module '<name>' not found
[timestamp] Component '<component>' not found in module '<module>'
```

#### Progress Indicators
```
[timestamp] Starting HOMESERVER update manager...
[timestamp] Mode: <mode>
[timestamp] Operation: <operation>
[timestamp] Target: <module>
[timestamp] Component: <component>
[timestamp] Using Python-based update system
[timestamp] Running <operation>...
```

#### Module Listing Output
```
[timestamp] Available modules:
[timestamp] --------------------------------------------------------------------------------
[timestamp] adblock         ENABLED    v1.1.0     Adblock module for Unbound DNS
[timestamp] website         DISABLED   v1.0.0     HOMESERVER website frontend/backend update system
[timestamp] --------------------------------------------------------------------------------
[timestamp] Total: 2 modules (1 enabled, 1 disabled)
```

## Flask Integration Examples

### Subprocess Execution
```python
import subprocess
import logging
from typing import Tuple, Optional

def execute_update_manager(mode: str = "full", target: str = None, component: str = None) -> Tuple[int, str, str]:
    """
    Execute updateManager.sh with specified mode
    
    Args:
        mode: "check", "legacy", "full", "enable", "disable", "list", "status"
        target: Module name for enable/disable/status operations
        component: Component name for component operations
    
    Returns:
        Tuple of (exit_code, stdout, stderr)
    """
    cmd = ["/usr/local/lib/updates/updateManager.sh"]
    
    if mode == "check":
        cmd.append("--check")
    elif mode == "legacy":
        cmd.append("--legacy")
    elif mode == "enable":
        cmd.extend(["--enable", target])
    elif mode == "disable":
        cmd.extend(["--disable", target])
    elif mode == "list":
        cmd.append("--list-modules")
    elif mode == "status":
        if target:
            cmd.extend(["--status", target])
        else:
            cmd.append("--status")
    # "full" mode uses no additional arguments
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "Update operation timed out"
    except Exception as e:
        return 1, "", f"Execution error: {str(e)}"

def check_updates_available() -> bool:
    """Check if updates are available without applying them"""
    exit_code, stdout, stderr = execute_update_manager("check")
    return exit_code == 0

def apply_updates() -> bool:
    """Apply available updates"""
    exit_code, stdout, stderr = execute_update_manager("full")
    if exit_code == 0:
        logging.info("Updates applied successfully")
        return True
    else:
        logging.error(f"Update failed: {stderr}")
        return False

def enable_module(module_name: str) -> bool:
    """Enable a specific module"""
    exit_code, stdout, stderr = execute_update_manager("enable", target=module_name)
    return exit_code == 0

def disable_module(module_name: str) -> bool:
    """Disable a specific module"""
    exit_code, stdout, stderr = execute_update_manager("disable", target=module_name)
    return exit_code == 0

def enable_component(module_name: str, component_name: str) -> bool:
    """Enable a specific component within a module"""
    cmd = ["/usr/local/lib/updates/updateManager.sh", "--enable-component", module_name, component_name]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result.returncode == 0
    except Exception:
        return False

def disable_component(module_name: str, component_name: str) -> bool:
    """Disable a specific component within a module"""
    cmd = ["/usr/local/lib/updates/updateManager.sh", "--disable-component", module_name, component_name]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result.returncode == 0
    except Exception:
        return False

def list_modules() -> dict:
    """Get list of all modules with their status"""
    cmd = ["/usr/local/lib/updates/updateManager.sh", "--list-modules"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return {
            "success": result.returncode == 0,
            "output": result.stdout,
            "error": result.stderr
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

def get_module_status(module_name: str) -> dict:
    """Get detailed status for a specific module"""
    cmd = ["/usr/local/lib/updates/updateManager.sh", "--status", module_name]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return {
            "success": result.returncode == 0,
            "output": result.stdout,
            "error": result.stderr
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
```

### Async Execution Pattern
```python
import asyncio
import subprocess

async def async_update_check() -> dict:
    """Asynchronously check for updates"""
    process = await asyncio.create_subprocess_exec(
        "/usr/local/lib/updates/updateManager.sh",
        "--check",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    stdout, stderr = await process.communicate()
    
    return {
        "exit_code": process.returncode,
        "stdout": stdout.decode(),
        "stderr": stderr.decode(),
        "success": process.returncode == 0
    }
```

## Error Handling

### Common Exit Codes
- **0:** Success
- **1:** General error (orchestrator missing, update failure)
- **124:** Timeout (if using subprocess timeout)

### Error Recovery
1. **Orchestrator Missing:** Verify Python system installation
2. **Permission Denied:** Ensure proper sudo/root privileges
3. **Network Errors:** Check Git repository accessibility
4. **Timeout:** Increase timeout values for large updates

## Security Considerations

### Privilege Requirements
- Script requires root privileges for system modifications
- Flask backend must handle privilege escalation appropriately
- Consider using sudo with NOPASSWD for specific operations

### Input Validation
- Only accept predefined mode parameters
- Validate command paths before execution
- Sanitize any user-provided input

## Monitoring and Logging

### Log Integration
- All operations produce timestamped logs
- Integrate with Flask logging system
- Consider log rotation for long-running operations

### Status Reporting
- Parse output for progress indicators
- Provide real-time status updates via WebSocket
- Store operation history for audit trails

## System Dependencies

### Required Components
- **Python 3:** For orchestrator execution
- **Git:** For repository synchronization
- **Bash:** For wrapper script execution
- **Root Access:** For system modifications

### File System Layout
```
/usr/local/lib/updates/
├── updateManager.sh          # Main CLI interface
├── index.py                  # Python orchestrator
├── modules/                  # Update modules
└── REMOTE.md                # This documentation
```

## Troubleshooting

### Common Issues
1. **"Python orchestrator not found"**
   - Verify `/usr/local/lib/updates/index.py` exists
   - Check file permissions

2. **Permission errors**
   - Ensure script runs with appropriate privileges
   - Verify file ownership and permissions

3. **Git synchronization failures**
   - Check network connectivity
   - Verify Git repository accessibility
   - Review authentication credentials

### Debug Mode
For detailed troubleshooting, examine the Python orchestrator directly:
```bash
python3 /usr/local/lib/updates/index.py --verbose
```

## Version Compatibility

This interface is designed for:
- **HOMESERVER:** v0.9.0+
- **Python:** 3.8+
- **Bash:** 4.0+

## Usage Examples

### Complete Module Management Workflow

```python
# Flask backend integration example
from typing import Dict, List
import subprocess
import logging

class UpdateManager:
    def __init__(self):
        self.cmd_base = "/usr/local/lib/updates/updateManager.sh"
    
    def get_all_modules(self) -> Dict:
        """Get comprehensive module listing"""
        result = subprocess.run([self.cmd_base, "--list-modules"], 
                              capture_output=True, text=True, timeout=30)
        return {
            "success": result.returncode == 0,
            "output": result.stdout,
            "modules": self._parse_module_list(result.stdout) if result.returncode == 0 else []
        }
    
    def toggle_module(self, module_name: str, enabled: bool) -> bool:
        """Toggle module enabled state"""
        action = "--enable" if enabled else "--disable"
        result = subprocess.run([self.cmd_base, action, module_name],
                              capture_output=True, text=True, timeout=30)
        return result.returncode == 0
    
    def toggle_component(self, module_name: str, component_name: str, enabled: bool) -> bool:
        """Toggle component enabled state"""
        action = "--enable-component" if enabled else "--disable-component"
        result = subprocess.run([self.cmd_base, action, module_name, component_name],
                              capture_output=True, text=True, timeout=30)
        return result.returncode == 0
    
    def get_module_details(self, module_name: str) -> Dict:
        """Get detailed module information including components"""
        result = subprocess.run([self.cmd_base, "--status", module_name],
                              capture_output=True, text=True, timeout=30)
        return {
            "success": result.returncode == 0,
            "output": result.stdout,
            "details": self._parse_module_status(result.stdout) if result.returncode == 0 else {}
        }
    
    def _parse_module_list(self, output: str) -> List[Dict]:
        """Parse module list output into structured data"""
        modules = []
        lines = output.split('\n')
        for line in lines:
            if line.strip() and not line.startswith('[') and not line.startswith('-'):
                parts = line.split()
                if len(parts) >= 4:
                    modules.append({
                        "name": parts[0],
                        "enabled": parts[1] == "ENABLED",
                        "version": parts[2].replace('v', ''),
                        "description": ' '.join(parts[3:])
                    })
        return modules
    
    def _parse_module_status(self, output: str) -> Dict:
        """Parse module status output into structured data"""
        # Implementation would parse the detailed status output
        # This is a simplified example
        return {"parsed": True, "raw_output": output}

# Usage in Flask routes
@app.route('/api/modules', methods=['GET'])
def get_modules():
    manager = UpdateManager()
    return jsonify(manager.get_all_modules())

@app.route('/api/modules/<module_name>/toggle', methods=['POST'])
def toggle_module(module_name):
    enabled = request.json.get('enabled', True)
    manager = UpdateManager()
    success = manager.toggle_module(module_name, enabled)
    return jsonify({"success": success})

@app.route('/api/modules/<module_name>/components/<component_name>/toggle', methods=['POST'])
def toggle_component(module_name, component_name):
    enabled = request.json.get('enabled', True)
    manager = UpdateManager()
    success = manager.toggle_component(module_name, component_name, enabled)
    return jsonify({"success": success})
```

### Command Line Examples

```bash
# System administration workflow
# 1. Check current module status
/usr/local/lib/updates/updateManager.sh --list-modules

# 2. Disable problematic module
/usr/local/lib/updates/updateManager.sh --disable website

# 3. Check specific module details
/usr/local/lib/updates/updateManager.sh --status website

# 4. Enable specific components only
/usr/local/lib/updates/updateManager.sh --enable-component website frontend
/usr/local/lib/updates/updateManager.sh --enable-component website backend
/usr/local/lib/updates/updateManager.sh --disable-component website premium

# 5. Re-enable module after fixes
/usr/local/lib/updates/updateManager.sh --enable website

# 6. Run updates (only enabled modules will be processed)
/usr/local/lib/updates/updateManager.sh
```

## Support

For integration issues or questions:
1. Review system logs in `/var/log/`
2. Check Python orchestrator documentation
3. Verify system dependencies and permissions 