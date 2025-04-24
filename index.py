import asyncio
import os
import sys
import importlib

# Import from the package root
from initialization.files.user_local_lib.updates import (
    load_manifest, 
    run_update, 
    run_updates_async, 
    log_message
)

async def run_all_updates():
    """
    Load the manifest and run all updates asynchronously based on entrypoint children.
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    manifest_path = os.path.join(base_dir, 'manifest.json')
    manifest = load_manifest(manifest_path)
    updates = {u['name']: u for u in manifest['updates']}
    entrypoint = manifest['entrypoint']
    entry = updates[entrypoint]
    
    update_configs = []
    for child_name in entry.get('children', []):
        child = updates.get(child_name)
        if not child:
            log_message(f"Child update '{child_name}' not found in manifest.", "WARNING")
            continue
        module_path = child.get('module')
        manifest_checksum = child.get('checksum')
        if not verify_module_checksum(child_name, manifest_checksum):
            log_message(f"Checksum mismatch for {child_name}! Skipping update.", "ERROR")
            continue
        args = child.get('args', [])
        
        if not module_path:
            log_message(f"No module specified for update '{child_name}'. Skipping.", "WARNING")
            continue
            
        update_configs.append({
            'module_path': module_path,
            'args': args,
            'name': child_name
        })
    
    if update_configs:
        log_message(f"Starting {len(update_configs)} updates")
        results = await run_updates_async(update_configs)
        log_message(f"All updates completed")
        return results
    else:
        log_message("No updates to run", "WARNING")
        return {}

def verify_module_checksum(module_name, manifest_checksum):
    """
    Import the module and compare its CHECKSUM with the manifest value.
    Returns True if they match, False otherwise.
    """
    try:
        mod = importlib.import_module(f"initialization.files.user_local_lib.updates.{module_name}")
        module_checksum = getattr(mod, "CHECKSUM", None)
        # Remove 'sha256:' prefix if present in manifest
        if manifest_checksum and manifest_checksum.startswith("sha256:"):
            manifest_checksum = manifest_checksum.split(":", 1)[1]
        return module_checksum == manifest_checksum
    except Exception as e:
        log_message(f"Checksum verification failed for {module_name}: {e}", "ERROR")
        return False

def main():
    """
    Main entry point for the update orchestrator.
    """
    try:
        # For Python 3.7+
        if sys.version_info >= (3, 7):
            return asyncio.run(run_all_updates())
        # For Python 3.6
        else:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(run_all_updates())
    except KeyboardInterrupt:
        log_message("Update process interrupted by user", "WARNING")
    except Exception as e:
        log_message(f"Unhandled error in update process: {e}", "ERROR")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
