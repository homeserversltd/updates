import os
import subprocess
from initialization.files.user_local_lib.updates import log_message
import json

with open(os.path.join(os.path.dirname(__file__), "paths.json")) as f:
    VENV_PATHS = json.load(f)

def update_venv(venv_name, venv_cfg):
    venv_path = venv_cfg["path"]
    packages = venv_cfg["packages"]
    upgrade_pip = venv_cfg.get("upgrade_pip", False)
    system_packages = venv_cfg.get("system_packages", False)

    log_message(f"Updating virtual environment: {venv_name}")

    # Create venv if missing
    if not os.path.isdir(venv_path):
        log_message(f"Creating virtual environment at {venv_path}")
        result = subprocess.run(["python3", "-m", "venv", venv_path], capture_output=True, text=True)
        if result.returncode != 0:
            log_message(f"Failed to create venv: {result.stderr}", "ERROR")
            return False

    # Activate venv
    activate_script = os.path.join(venv_path, "bin", "activate")
    if not os.path.isfile(activate_script):
        log_message(f"Activation script not found at {activate_script}", "ERROR")
        return False

    # Build pip install command
    pip_cmd = f". '{activate_script}'; "
    if upgrade_pip:
        pip_cmd += "pip install --upgrade pip; "
    pip_cmd += "pip install --upgrade "
    if system_packages:
        pip_cmd += "--system-site-packages "
    pip_cmd += " ".join(packages)
    pip_cmd += "; deactivate"

    # Run the command in a shell
    result = subprocess.run(["bash", "-c", pip_cmd], capture_output=True, text=True)
    if result.returncode != 0:
        log_message(f"Failed to update venv {venv_name}: {result.stderr}", "ERROR")
        return False
    log_message(f"Finished updating {venv_name}")
    log_message("----------------------------------------")
    return True

def main(args=None):
    """
    Main entry point for venvs update module.
    Args:
        args: List of arguments (unused)
    Returns:
        dict: Status and results of the update
    """
    log_message("Starting virtual environment updates...")
    results = {}
    for venv_name, venv_cfg in VENV_PATHS.items():
        success = update_venv(venv_name, venv_cfg)
        results[venv_name] = success
    log_message("All virtual environments have been updated.")
    return results

if __name__ == "__main__":
    main()
