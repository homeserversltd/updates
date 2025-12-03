# Contributing to HOMESERVER Updates Orchestrator

Thank you for your interest in contributing to the HOMESERVER Updates Orchestrator. This system manages schema-driven updates for the entire HOMESERVER platform, and we welcome contributions that improve reliability, functionality, and the update experience.

## About This Repository

The Updates Orchestrator provides enterprise-grade update management:
- Schema-version driven update detection
- Git repository synchronization
- Atomic module updates with rollback
- Universal module execution for all enabled services
- Self-updating capability
- Modular architecture for extensibility

**Importance**: This system keeps HOMESERVER installations current and functioning. Issues can affect:
- Platform updates and security patches
- Service configuration and availability
- System stability and reliability
- User experience across all HOMESERVER installations

We prioritize backward compatibility, reliability, and thorough testing.

## Ways to Contribute

### High-Value Contributions

- **Bug fixes**: Address update failures, edge cases, or synchronization issues
- **Reliability improvements**: Better error handling, rollback, or state management
- **New modules**: Create update modules for HOMESERVER services
- **Core improvements**: Enhance orchestration logic, performance, or architecture
- **Documentation**: Clarify module development, update process, or architecture
- **Testing**: Validate updates across different configurations
- **Maintenance tasks**: Contribute maintenance modules for services

### Module Contributions

The most common contribution is creating or improving update modules. Each module:
- Manages updates for a specific service or component
- Is self-contained with its own logic and configuration
- Runs every update cycle (not just when code changes)
- Handles service configuration, restarts, and validation

## Getting Started

### Prerequisites

- **Python 3.9+**: Core language for orchestrator and modules
- **Git knowledge**: Repository sync and version control
- **Linux administration**: System administration experience
- **HOMESERVER familiarity**: Understanding of platform architecture (helpful)
- **Testing environment**: VM or test system for validation

### Repository Setup

1. **Fork the repository** on GitHub:
   ```bash
   git clone git@github.com:YOUR_USERNAME/updates.git
   cd updates
   ```

2. **Add upstream remote**:
   ```bash
   git remote add upstream git@github.com:homeserversltd/updates.git
   ```

3. **Study the architecture**: Review README.md and existing modules

4. **Examine existing modules**: Look at `modules/` directory for patterns

## Development Workflow

### 1. Create a Feature Branch

```bash
git checkout -b feature/your-feature-name
# or
git checkout -b module/service-name
# or
git checkout -b fix/issue-description
```

### 2. Make Your Changes

See specific sections below for:
- Creating new modules
- Improving the orchestrator
- Adding maintenance tasks

### 3. Test Thoroughly

Testing is **mandatory**. See [Testing Requirements](#testing-requirements).

### 4. Commit and Push

```bash
git add .
git commit -m "Descriptive commit message"
git push origin feature/your-feature-name
```

### 5. Open a Pull Request

Include comprehensive description and testing details.

## Creating Update Modules

### Module Structure

Every module needs these files:

```
modules/your_service/
├── index.json          # Module metadata and configuration
├── index.py           # Main module logic
├── __init__.py        # (Optional) Package initialization
├── README.md          # (Optional) Module documentation
└── maintenance.py     # (Optional) Maintenance tasks
```

### Module index.json

```json
{
    "metadata": {
        "schema_version": "1.0.0",
        "name": "your_service",
        "description": "Brief description of what this module manages",
        "enabled": true
    },
    "configuration": {
        "service_name": "your_service",
        "config_path": "/etc/your_service/config.json",
        "data_dir": "/var/lib/your_service",
        "backup_paths": [
            "/etc/your_service/",
            "/var/lib/your_service/"
        ]
    }
}
```

### Module index.py

```python
"""
Your Service Update Module

This module manages updates and configuration for your_service.
It runs during every update cycle to ensure the service is properly configured.
"""

from typing import Dict, Any, Optional
from updates.utils.permissions import PermissionManager, PermissionTarget
from updates.utils.index import log_message
import subprocess
import json
import os


def restore_service_permissions() -> bool:
    """Restore proper permissions after update."""
    try:
        permission_manager = PermissionManager("your_service")
        
        targets = [
            PermissionTarget(
                path="/opt/your_service",
                owner="service_user",
                group="service_group",
                mode=0o755,
                recursive=True
            ),
            PermissionTarget(
                path="/var/lib/your_service",
                owner="service_user",
                group="service_group",
                mode=0o755,
                recursive=True
            ),
            PermissionTarget(
                path="/etc/your_service/config.json",
                owner="service_user",
                group="service_group",
                mode=0o640,
                target_type="file"
            )
        ]
        
        return permission_manager.set_permissions(targets)
    except Exception as e:
        log_message(f"Permission restoration failed: {e}", "ERROR")
        return False


def update_service_configuration() -> bool:
    """Update service configuration if needed."""
    try:
        config_path = "/etc/your_service/config.json"
        
        # Read current configuration
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        # Make any necessary updates
        updated = False
        if "new_setting" not in config:
            config["new_setting"] = "default_value"
            updated = True
        
        # Write back if changed
        if updated:
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
            log_message("Updated service configuration")
        
        return True
    except Exception as e:
        log_message(f"Configuration update failed: {e}", "ERROR")
        return False


def restart_service_if_needed() -> bool:
    """Restart service if configuration changed."""
    try:
        result = subprocess.run(
            ["systemctl", "restart", "your_service.service"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            log_message("Service restarted successfully")
            return True
        else:
            log_message(f"Service restart failed: {result.stderr}", "ERROR")
            return False
            
    except subprocess.TimeoutExpired:
        log_message("Service restart timed out", "ERROR")
        return False
    except Exception as e:
        log_message(f"Service restart error: {e}", "ERROR")
        return False


def validate_service_status() -> bool:
    """Verify service is running properly."""
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "your_service.service"],
            capture_output=True,
            text=True
        )
        
        is_active = result.returncode == 0
        if not is_active:
            log_message("Service is not active", "WARNING")
        
        return is_active
    except Exception as e:
        log_message(f"Service validation failed: {e}", "ERROR")
        return False


def main(args: Optional[Any] = None) -> Dict[str, Any]:
    """
    Main entry point for module execution.
    
    This function is called during every update cycle for enabled modules.
    It should be idempotent and handle both initial setup and ongoing maintenance.
    
    Args:
        args: Optional command line arguments
    
    Returns:
        dict: Status dictionary with success/error information
        False: Signal that module needs to restart after self-update
    """
    log_message("Executing your_service update module...")
    
    try:
        # Update configuration if needed
        if not update_service_configuration():
            return {"success": False, "error": "Configuration update failed"}
        
        # Restart service if configuration changed
        # (You might want to check if restart is actually needed)
        if not restart_service_if_needed():
            return {"success": False, "error": "Service restart failed"}
        
        # Validate service is running
        if not validate_service_status():
            log_message("Service validation failed, but continuing", "WARNING")
        
        # Always restore permissions after changes
        if not restore_service_permissions():
            log_message("Warning: Permission restoration failed", "WARNING")
        
        log_message("your_service update module completed successfully")
        return {"success": True}
        
    except Exception as e:
        log_message(f"Module execution failed: {e}", "ERROR")
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    # Allow module to be run standalone for testing
    result = main()
    print(f"Module result: {result}")
```

### Module Best Practices

**Design Principles:**
- **Idempotent**: Safe to run multiple times
- **Self-contained**: No dependencies on other modules
- **Comprehensive error handling**: Never crash the orchestrator
- **Proper logging**: Use log_message() for all important operations
- **Permission management**: Always restore permissions
- **Service validation**: Verify service health after changes

**What Modules Should Do:**
- Check and update configuration files
- Restart services when needed
- Validate service functionality
- Restore proper file permissions
- Handle missing or corrupted files gracefully

**What Modules Should NOT Do:**
- Assume other modules have run
- Make cross-module calls
- Ignore errors silently
- Leave services in broken states
- Hardcode paths or credentials

## Adding Maintenance Tasks

Modules can include optional `maintenance.py` for routine maintenance:

```python
"""
Your Service Maintenance Tasks

Runs automatically during every update cycle.
"""

import os
import subprocess
from typing import Dict, Any
from datetime import datetime, timedelta
from updates.utils.index import log_message


class YourServiceMaintenance:
    """Maintenance tasks for your_service."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.service_name = config.get("service_name", "your_service")
    
    def run_maintenance(self) -> Dict[str, Any]:
        """Run all maintenance tasks."""
        results = {
            "module": self.service_name,
            "success": True,
            "tasks": {},
            "timestamp": datetime.now().isoformat(),
            "errors": []
        }
        
        try:
            # Task 1: Clean up old logs
            log_message(f"Running maintenance for {self.service_name}...")
            results["tasks"]["cleanup"] = self._cleanup_old_logs()
            
            # Task 2: Validate configuration
            results["tasks"]["validate"] = self._validate_configuration()
            
            # Task 3: Check service health
            results["tasks"]["health"] = self._check_service_health()
            
        except Exception as e:
            log_message(f"Maintenance failed: {e}", "ERROR")
            results["success"] = False
            results["errors"].append(str(e))
        
        return results
    
    def _cleanup_old_logs(self) -> Dict[str, Any]:
        """Clean up old log files."""
        try:
            log_dir = f"/var/log/{self.service_name}"
            cutoff_date = datetime.now() - timedelta(days=30)
            
            cleaned_count = 0
            for log_file in os.listdir(log_dir):
                if log_file.endswith('.log'):
                    file_path = os.path.join(log_dir, log_file)
                    if os.path.getmtime(file_path) < cutoff_date.timestamp():
                        os.remove(file_path)
                        cleaned_count += 1
            
            return {
                "success": True,
                "cleaned_count": cleaned_count
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _validate_configuration(self) -> Dict[str, Any]:
        """Validate service configuration."""
        try:
            config_path = self.config.get("config_path")
            if not config_path or not os.path.exists(config_path):
                return {
                    "success": False,
                    "error": f"Configuration file not found: {config_path}"
                }
            
            # Add specific validation logic here
            return {"success": True, "config_valid": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _check_service_health(self) -> Dict[str, Any]:
        """Check if service is healthy."""
        try:
            result = subprocess.run(
                ["systemctl", "is-active", "--quiet", f"{self.service_name}.service"],
                capture_output=True
            )
            
            is_active = result.returncode == 0
            
            return {
                "success": True,
                "service_active": is_active
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
```

## Testing Requirements

**Comprehensive testing is required for all contributions.**

### For New Modules

```markdown
## Module Testing Performed

### Functional Tests
- Module executes successfully: SUCCESS
- Service configuration updated: VERIFIED
- Service restarted properly: SUCCESS
- Permissions restored correctly: VERIFIED

### Idempotency Tests
- Ran module 3 times consecutively: NO ERRORS
- Service remained stable: CONFIRMED
- No duplicate configuration: VERIFIED

### Error Handling Tests
- Missing configuration file: HANDLED gracefully
- Service restart failure: ERROR reported correctly
- Permission issues: LOGGED appropriately

### Integration Tests
- Works with orchestrator: VERIFIED
- Compatible with other modules: TESTED
- Doesn't affect other services: CONFIRMED

### Test Environment
- OS: Debian 12
- HOMESERVER version: [version]
- Service version: [version]

### Test Methodology
[Describe your testing process]
```

### For Core Changes

Test impact on:
- Existing modules
- Update orchestration flow
- Rollback functionality
- Performance
- Backward compatibility

## Commit Message Guidelines

Clear, informative commit messages:

```
Add update module for Jellyfin service

Created new update module to manage Jellyfin configuration:
- Monitors and updates jellyfin.conf settings
- Restarts service when configuration changes
- Validates service health after restart
- Includes maintenance tasks for log cleanup

Module features:
- index.json: Module metadata and schema version 1.0.0
- index.py: Core update logic with error handling
- maintenance.py: Automatic log cleanup and health checks

Testing:
- Tested module execution: SUCCESS
- Verified idempotency: PASSED
- Service restart: WORKING
- Permission management: CORRECT

Integrated with updates orchestrator v2.0+
```

## Pull Request Process

### PR Description Template

```markdown
## Summary
Brief description of your contribution.

## Type of Contribution
- [ ] New module
- [ ] Core improvement
- [ ] Bug fix
- [ ] Documentation
- [ ] Maintenance task

## Changes Made
- Specific change 1
- Specific change 2

## Testing Performed
[Use appropriate testing template above]

## Backward Compatibility
Is this change backward compatible?

## Documentation Updates
What documentation was added/updated?

## Checklist
- [ ] Code follows Python best practices
- [ ] Type hints included
- [ ] Error handling is comprehensive
- [ ] Logging is appropriate
- [ ] Module is idempotent (if applicable)
- [ ] Permissions handled correctly
- [ ] Tested thoroughly
- [ ] Documentation updated
```

### Review Process

1. **Code review**: Check quality, reliability, architecture fit
2. **Testing**: May request additional testing
3. **Integration**: Verify compatibility with orchestrator
4. **Discussion**: Collaborate on improvements
5. **Approval**: Merge after satisfactory review

## Architecture Understanding

### Three-Phase Update Process

1. **Phase 1: Schema Updates** - Update modules with newer schema versions
2. **Phase 2: Universal Execution** - Run ALL enabled modules
3. **Phase 3: Self-Updates** - Handle modules that need restart

### Key Concepts

- **Schema version**: Determines when module code is updated
- **Enabled flag**: Controls whether module runs during execution
- **Module execution**: Happens every cycle for enabled modules
- **Maintenance**: Optional routine tasks run automatically

### Utility Functions

- **Permissions**: `utils/permissions.py` for permission management
- **Logging**: `utils/index.py` for consistent logging
- **State**: `utils/state_manager.py` for backup/restore

## Getting Help

### Resources

- **README**: Comprehensive system documentation
- **Existing modules**: Study patterns in `modules/` directory
- **Utility modules**: Review `utils/` for helper functions

### Questions?

- **Open an issue**: General questions or feature discussions
- **Email**: Complex architectural questions (owner@arpaservers.com)
- **Study code**: Review existing modules and orchestrator

## Recognition

Contributors:
- Are credited in the repository
- Help keep HOMESERVER installations current and secure
- Build professional software engineering portfolio
- Contribute to digital sovereignty infrastructure

## License

This project is licensed under **GPL-3.0**. Contributions are accepted under this license, and no CLA is required.

---

**Thank you for contributing to HOMESERVER update infrastructure!**

Your work keeps the platform current, secure, and reliable for users worldwide.

*HOMESERVER LLC - Professional Digital Sovereignty Solutions*

