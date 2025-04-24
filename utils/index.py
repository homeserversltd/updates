import datetime
import sys
import hashlib
import os

def log_message(message, level="INFO"):
    """
    Log a message with a timestamp and level to stdout.
    Args:
        message (str): The message to log.
        level (str): Log level (e.g., 'INFO', 'ERROR').
    """
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}", file=sys.stdout)

def compute_folder_sha256(folder_path, exclude_files=None):
    """
    Compute a SHA-256 hash of all files in a folder (recursively), excluding specified files.
    The hash is updated with both the relative file path and file contents for reproducibility.
    """
    if exclude_files is None:
        exclude_files = {"checksum", "checksum.sha", "__pycache__"}
    sha256 = hashlib.sha256()
    for root, dirs, files in os.walk(folder_path):
        # Exclude __pycache__ directories
        dirs[:] = [d for d in dirs if d not in exclude_files]
        for fname in sorted(files):
            if fname in exclude_files or fname.endswith('.pyc'):
                continue
            fpath = os.path.join(root, fname)
            relpath = os.path.relpath(fpath, folder_path)
            sha256.update(relpath.encode('utf-8'))
            with open(fpath, 'rb') as f:
                while True:
                    chunk = f.read(8192)
                    if not chunk:
                        break
                    sha256.update(chunk)
    return sha256.hexdigest()

# Add more shared utility functions here as needed. 