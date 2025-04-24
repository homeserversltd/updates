"""
Updates Orchestrator System

This package provides a modular, manifest-driven update orchestration system.
It enables robust, maintainable, and extensible management of service/component updates.
See README.md for architecture and usage details.
"""

import json
import importlib
import traceback
import os
import sys
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Optional, Callable

# Import shared utilities
from .utils.index import log_message

# Re-export utilities for easy access by submodules
__all__ = ['log_message', 'run_update', 'run_updates_async', 'load_manifest']

def load_manifest(manifest_path=None):
    """
    Load the manifest file containing update configurations.
    
    Args:
        manifest_path: Path to manifest file. If None, uses default location.
        
    Returns:
        dict: The loaded manifest data
    """
    if manifest_path is None:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        manifest_path = os.path.join(base_dir, 'manifest.json')
    
    with open(manifest_path, 'r') as f:
        return json.load(f)

def run_update(module_path, args=None, callback=None):
    """
    Run a single update module.
    
    Args:
        module_path (str): Import path to the module
        args (list, optional): Arguments to pass to the module's main function
        callback (callable, optional): Function to call when update completes
        
    Returns:
        Any: Result from the update function
    """
    result = None
    try:
        if not module_path.startswith("initialization.files.user_local_lib.updates"):
            module_path = f"initialization.files.user_local_lib.updates.{module_path}"
        
        mod = importlib.import_module(module_path)
        if hasattr(mod, 'main'):
            log_message(f"Running update: {module_path}")
            result = mod.main(args)
            log_message(f"Completed update: {module_path}")
        else:
            log_message(f"Module {module_path} has no main(args) function.", "ERROR")
    except Exception as e:
        log_message(f"Error running update for {module_path}: {e}", "ERROR")
        traceback.print_exc()
    
    if callback and callable(callback):
        callback(module_path, result)
    
    return result

async def run_updates_async(updates, max_workers=None):
    """
    Run multiple updates asynchronously using a thread pool.
    
    Args:
        updates (list): List of dicts with 'module_path' and 'args' keys
        max_workers (int, optional): Maximum number of concurrent workers
        
    Returns:
        dict: Mapping of module paths to their results
    """
    results = {}
    
    def update_callback(module_path, result):
        results[module_path] = result
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        loop = asyncio.get_event_loop()
        futures = []
        
        for update in updates:
            module_path = update.get('module_path')
            args = update.get('args', [])
            future = loop.run_in_executor(
                executor,
                lambda mp=module_path, a=args: run_update(mp, a, update_callback)
            )
            futures.append(future)
        
        await asyncio.gather(*futures)
    
    return results

# Initialize package-level variables
manifest = None 