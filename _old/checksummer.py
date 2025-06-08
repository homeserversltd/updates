import os
from initialization.files.user_local_lib.updates.utils.index import compute_folder_sha256

def update_module_checksums(updates_dir):
    """
    For each subdirectory in updates_dir, compute the SHA-256 checksum and write it to a 'checksum' file.
    Print the module name and checksum in 'sha256:<hash>' format for manifest updating.
    """
    for module_name in sorted(os.listdir(updates_dir)):
        module_path = os.path.join(updates_dir, module_name)
        if not os.path.isdir(module_path):
            continue
        # Skip utils and other non-module folders
        if module_name in {"__pycache__", "utils"}:
            continue
        checksum = compute_folder_sha256(module_path)
        checksum_file = os.path.join(module_path, "checksum")
        with open(checksum_file, "w") as f:
            f.write(checksum + "\n")
        print(f"{module_name}: sha256:{checksum}")

if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    updates_dir = base_dir
    update_module_checksums(updates_dir)
