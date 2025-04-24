import subprocess
from initialization.files.user_local_lib.updates import log_message

def check_updates():
    """
    Check for available package updates.
    Returns:
        int: Number of upgradable packages
        str: List of upgradable packages (if any)
    """
    try:
        result = subprocess.run([
            "apt", "list", "--upgradable"
        ], capture_output=True, text=True)
        if result.returncode == 0:
            lines = result.stdout.strip().splitlines()
            # The first line is 'Listing...'
            upgradable = lines[1:] if len(lines) > 1 else []
            return len(upgradable), "\n".join(upgradable)
        else:
            log_message(f"Failed to check for updates: {result.stderr}", "ERROR")
            return -1, "apt list failed"
    except Exception as e:
        log_message(f"Error during update check: {e}", "ERROR")
        return -1, str(e)

def run_apt_update():
    """
    Run apt update/upgrade/autoremove/clean. Log all output and errors.
    Returns:
        bool: True if successful, False otherwise
    """
    steps = [
        ("Updating package lists", ["apt", "update"]),
        ("Upgrading packages", ["apt", "upgrade", "-y"]),
        ("Autoremoving unused packages", ["apt", "autoremove", "-y"]),
        ("Cleaning up", ["apt", "clean"])
    ]
    for desc, cmd in steps:
        log_message(desc)
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                log_message(f"{desc} failed: {result.stderr}", "ERROR")
                return False
            else:
                log_message(result.stdout)
        except Exception as e:
            log_message(f"{desc} error: {e}", "ERROR")
            return False
    return True

def main(args=None):
    """
    Main entry point for OS update module.
    Args:
        args: List of arguments (supports '--check')
    Returns:
        dict: Status and results of the update
    """
    if args is None:
        args = []
    if len(args) > 0 and args[0] == "--check":
        count, upgradable = check_updates()
        if count > 0:
            log_message(f"{count} package(s) can be upgraded:\n{upgradable}")
            return {"success": True, "upgradable": count, "details": upgradable}
        elif count == 0:
            log_message("No packages to upgrade.")
            return {"success": True, "upgradable": 0}
        else:
            log_message("Failed to check for updates.", "ERROR")
            return {"success": False, "error": upgradable}
    # Normal update mode
    log_message("Starting Debian OS update...")
    success = run_apt_update()
    if success:
        log_message("Debian OS update completed successfully!")
        return {"success": True}
    else:
        log_message("Debian OS update failed.", "ERROR")
        return {"success": False}

if __name__ == "__main__":
    main()
