initialization/files/user_local_lib/updates/README.md
Updates Orchestrator System
Overview
This directory implements a modular, Python-based update orchestration system for managing and updating various services and components in a robust, maintainable, and extensible way. The system is designed to allow updates to be run from a single entrypoint, with each update module being self-contained and responsible for its own sub-updates.
Key Features
Manifest-driven:
Updates and their relationships are defined in a manifest.json file, which specifies the update modules, their arguments, and their child dependencies.
Python modules:
Each update is implemented as a Python module (with an index.py), allowing for complex logic, error handling, and integration with Python’s ecosystem.
Self-contained submodules:
The master index.py only calls the top-level children defined in the manifest. Each submodule is responsible for invoking its own children, ensuring that a failure in one module does not halt the entire update process.
Robust error handling:
If a submodule fails, the error is logged, but the orchestrator continues with the next update, maximizing the chance that as many updates as possible succeed.
Extensible:
New update modules can be added by creating a new subdirectory with an index.py and updating the manifest. No changes to the orchestrator are required.
Directory Structure
manifest.json
The manifest file describing all update modules, their arguments, and their child relationships.
index.py
The master orchestrator script. Reads the manifest and runs the top-level updates.
<module_name>/index.py
Each update module is a subdirectory with its own index.py containing a main(args) function. Modules can read the manifest and invoke their own children as needed.
Example manifest.json
{
"updates": [
{
"name": "adblock",
"module": "adblock.index",
"args": [],
"children": []
},
{
"name": "atuin",
"module": "atuin.index",
"args": [],
"children": []
},
{
"name": "filebrowser",
"module": "filebrowser.index",
"args": [],
"children": []
},
{
"name": "gogs",
"module": "gogs.index",
"args": [],
"children": []
},
{
"name": "all_services",
"module": "",
"args": [],
"children": [
"adblock",
"atuin",
"filebrowser",
"gogs"
]
}
],
"entrypoint": "all_services"
}
How it Works
The master index.py reads manifest.json and runs each child of the entrypoint.
Each update module (e.g., adblock/index.py) implements a main(args) function and is responsible for running its own children (if any).
If a module fails, the error is logged, but the orchestrator continues with the next module.
This design ensures that updates are modular, maintainable, and robust against partial failures.
Adding a New Update Module
Create a new subdirectory under updates/ (e.g., foobar/).
Add an index.py with a main(args) function.
Add an entry for your module in manifest.json, and add it as a child to the appropriate parent.
Your module can optionally read the manifest and invoke its own children.
Example index.py for a Module
def main(args=None):
print("Running update for this module...")
# Module-specific update logic here
Best Practices
Keep each module self-contained and idempotent.
Handle errors within each module and log them appropriately.
Only the master index.py should orchestrate top-level updates; submodules handle their own children.
Use the manifest as the single source of truth for update relationships.
License
This system is intended for internal use. Adapt and extend as needed for your environment.